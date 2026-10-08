"""Modul retrieval hybrid (Dense BGE-M3 + BM25 via Reciprocal Rank Fusion).

Mendukung filter metadata, deduplikasi dokumen kembar (also_in),
pemangkasan batas konteks maksimum, dan gerbang penolakan relevansi rendah.
"""

import logging
import sqlite3
import time
from typing import Any, Callable, Optional, Union

import numpy as np
from pydantic import BaseModel, Field

from app import ollama_client
from app.config import Settings, get_settings
import app.store as store

logger = logging.getLogger(__name__)


class Filters(BaseModel):
    """Filter metadata untuk mempersempit ruang pencarian retrieval."""

    folders: Optional[list[str]] = None
    file_types: Optional[list[str]] = None
    doc_ids: Optional[list[str]] = None


class Hit(BaseModel):
    """Representasi satu potongan chunk hasil pencarian dengan metrik relevansi."""

    rowid: int
    chunk_id: str
    doc_id: str
    filename: str
    rel_path: str
    location: str
    text: str
    file_hash: str
    idx: int
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rrf_score: float = 0.0
    dense_rank: Optional[int] = None
    bm25_rank: Optional[int] = None
    also_in: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    """Hasil akhir proses retrieval beserta status gerbang penolakan dan latensi."""

    hits: list[Hit] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: Optional[str] = None
    timing: dict[str, float] = Field(default_factory=dict)


def retrieve(
    query: str,
    filters: Optional[Filters] = None,
    top_k: Optional[int] = None,
    mode: str = "hybrid",  # "hybrid", "dense", "bm25"
    settings: Optional[Settings] = None,
    conn: Optional[sqlite3.Connection] = None,
    vindex: Optional[store.VectorIndex] = None,
    embed_fn: Optional[Callable[[list[str], str], list[list[float]]]] = None,
) -> RetrievalResult:
    """Melakukan pencarian hybrid terpadu dengan RRF dan penyaringan relevansi."""
    if settings is None:
        settings = get_settings()

    target_top_k = top_k or settings.TOP_K
    candidates_k = settings.CANDIDATES
    rrf_k = settings.RRF_K

    close_conn = False
    if conn is None:
        db_path = settings.INDEX_DIR / "index.db"
        conn = store.get_connection(db_path)
        close_conn = True

    try:
        if vindex is None:
            vindex = store.VectorIndex(dtype=settings.VECTOR_DTYPE)
            vindex.load_from_db(conn)
        else:
            vindex.refresh_if_stale(conn)

        # 1. Pencarian Dense Vector (BGE-M3)
        dense_results: list[tuple[int, float]] = []
        embed_ms = 0.0
        if mode in ("hybrid", "dense"):
            t_emb_0 = time.perf_counter()
            if embed_fn is not None:
                q_vec = embed_fn([query], "query")[0]
            else:
                q_vec = ollama_client.embed([query], kind="query")[0]
            embed_ms = (time.perf_counter() - t_emb_0) * 1000.0

            q_arr = np.array(q_vec, dtype=np.float32)
            dense_results = vindex.search(
                q_arr,
                k=candidates_k,
                folders=filters.folders if filters else None,
                file_types=filters.file_types if filters else None,
                doc_ids=filters.doc_ids if filters else None,
            )

        # 2. Pencarian Lexical BM25 (FTS5)
        t_search_0 = time.perf_counter()
        bm25_results: list[tuple[int, float]] = []
        if mode in ("hybrid", "bm25"):
            bm25_results = store.bm25_search(
                conn,
                query,
                k=candidates_k,
                folders=filters.folders if filters else None,
                file_types=filters.file_types if filters else None,
                doc_ids=filters.doc_ids if filters else None,
            )
        search_ms = (time.perf_counter() - t_search_0) * 1000.0

        # 3. Gerbang Penolakan (Relevance Gate)
        # Tolak HANYA bila kedua sinyal lemah: dense < MIN_DENSE_SCORE dan BM25 <= MIN_BM25_SCORE
        top_dense = dense_results[0][1] if dense_results else 0.0
        top_bm25 = bm25_results[0][1] if bm25_results else -1.0

        dense_weak = top_dense < settings.MIN_DENSE_SCORE
        bm25_weak = (not bm25_results) or (top_bm25 <= settings.MIN_BM25_SCORE)

        if mode == "hybrid" and dense_weak and bm25_weak:
            logger.info("Gerbang penolakan aktif: relevansi dense (%.3f) dan BM25 (%.3f) terlalu rendah.", top_dense, top_bm25)
            return RetrievalResult(
                hits=[],
                refused=True,
                refusal_reason="low_relevance",
                timing={"embed_ms": round(embed_ms, 2), "search_ms": round(search_ms, 2)},
            )
        elif mode == "dense" and dense_weak:
            return RetrievalResult(
                hits=[],
                refused=True,
                refusal_reason="low_relevance",
                timing={"embed_ms": round(embed_ms, 2), "search_ms": round(search_ms, 2)},
            )
        elif mode == "bm25" and bm25_weak:
            return RetrievalResult(
                hits=[],
                refused=True,
                refusal_reason="low_relevance",
                timing={"embed_ms": round(embed_ms, 2), "search_ms": round(search_ms, 2)},
            )

        # 4. Penggabungan Peringkat (RRF / Mode Tertentu)
        dense_ranks = {rowid: r for r, (rowid, _) in enumerate(dense_results, start=1)}
        dense_scores = {rowid: score for rowid, score in dense_results}
        bm25_ranks = {rowid: r for r, (rowid, _) in enumerate(bm25_results, start=1)}
        bm25_scores = {rowid: score for rowid, score in bm25_results}

        all_candidate_rowids = set(dense_ranks.keys()) | set(bm25_ranks.keys())

        scored_candidates: list[dict[str, Any]] = []
        for rowid in all_candidate_rowids:
            d_rank = dense_ranks.get(rowid)
            b_rank = bm25_ranks.get(rowid)

            if mode == "hybrid":
                rrf_score = 0.0
                if d_rank is not None:
                    rrf_score += 1.0 / (rrf_k + d_rank)
                if b_rank is not None:
                    rrf_score += 1.0 / (rrf_k + b_rank)
                final_score = rrf_score
            elif mode == "dense":
                final_score = dense_scores.get(rowid, 0.0)
                rrf_score = final_score
            else:  # bm25
                final_score = bm25_scores.get(rowid, 0.0)
                rrf_score = final_score

            scored_candidates.append({
                "rowid": rowid,
                "final_score": final_score,
                "rrf_score": rrf_score,
                "dense_score": dense_scores.get(rowid),
                "bm25_score": bm25_scores.get(rowid),
                "dense_rank": d_rank,
                "bm25_rank": b_rank,
            })

        # Urutkan berdasarkan skor akhir tertinggi
        scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)

        # 5. Deduplikasi Dokumen Kembar (also_in)
        unique_hits: list[Hit] = []
        seen_chunks: dict[tuple[str, int], Hit] = {}  # (file_hash, idx) -> Hit

        for cand in scored_candidates:
            ch_data = store.get_chunk_by_rowid(conn, cand["rowid"])
            if not ch_data:
                continue

            doc_data = store.get_document(conn, ch_data["doc_id"])
            if not doc_data:
                continue

            hash_key = (doc_data["file_hash"], ch_data["idx"])
            if hash_key in seen_chunks:
                # Catat path dokumen kembarannya di also_in
                prior_hit = seen_chunks[hash_key]
                if doc_data["rel_path"] not in prior_hit.also_in and doc_data["rel_path"] != prior_hit.rel_path:
                    prior_hit.also_in.append(doc_data["rel_path"])
                continue

            hit = Hit(
                rowid=cand["rowid"],
                chunk_id=ch_data["chunk_id"],
                doc_id=ch_data["doc_id"],
                filename=doc_data["filename"],
                rel_path=doc_data["rel_path"],
                location=ch_data["location"],
                text=ch_data["text"],
                file_hash=doc_data["file_hash"],
                idx=ch_data["idx"],
                dense_score=cand["dense_score"],
                bm25_score=cand["bm25_score"],
                rrf_score=cand["rrf_score"],
                dense_rank=cand["dense_rank"],
                bm25_rank=cand["bm25_rank"],
                also_in=[],
            )
            seen_chunks[hash_key] = hit
            unique_hits.append(hit)

        # 6. Pemotongan Batas Konteks Maksimum (MAX_CONTEXT_CHARS)
        final_hits: list[Hit] = []
        accumulated_chars = 0
        for h in unique_hits[:target_top_k]:
            if accumulated_chars + len(h.text) > settings.MAX_CONTEXT_CHARS and final_hits:
                logger.info(
                    "Pemotongan konteks: chunk %s dilewati karena melebihi batas %d karakter",
                    h.chunk_id,
                    settings.MAX_CONTEXT_CHARS,
                )
                break
            final_hits.append(h)
            accumulated_chars += len(h.text)

        return RetrievalResult(
            hits=final_hits,
            refused=False,
            refusal_reason=None,
            timing={"embed_ms": round(embed_ms, 2), "search_ms": round(search_ms, 2)},
        )

    finally:
        if close_conn:
            conn.close()
