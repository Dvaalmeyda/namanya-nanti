"""Endpoint pencarian dokumen (Retrieval Only) tanpa pemanggilan model LLM."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings, get_db_conn, get_vector_index, verify_api_key
from app.api.schemas import SearchHitItem, SearchRequest, SearchResponse
from app.config import Settings
from app.retrieval import Filters, retrieve
from app import store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Search"], dependencies=[Depends(verify_api_key)])


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Pencarian retrieval dokumen murni",
    description="Melakukan pencarian potongan dokumen menggunakan Dense Vektor, BM25, atau Hybrid (RRF) tanpa memanggil LLM. Menghasilkan skor relevansi dan cuplikan teks 200 karakter.",
)
def search_documents(
    req: SearchRequest,
    settings: Settings = Depends(get_app_settings),
    vindex: store.VectorIndex = Depends(get_vector_index),
) -> SearchResponse:
    """Mengeksekusi pencarian potongan dokumen berbasis konfigurasi."""
    filters = None
    if req.filters:
        filters = Filters(
            folders=req.filters.folders,
            file_types=req.filters.file_types,
            doc_ids=req.filters.doc_ids,
        )

    ret_res = retrieve(
        query=req.query,
        filters=filters,
        top_k=req.top_k,
        mode=req.mode,
        settings=settings,
        vindex=vindex,
    )

    hits_items: list[SearchHitItem] = []
    for rank, h in enumerate(ret_res.hits, start=1):
        snippet = h.text[:200].replace("\r", " ").strip()
        hits_items.append(
            SearchHitItem(
                rank=rank,
                chunk_id=h.chunk_id,
                doc_id=h.doc_id,
                rel_path=h.rel_path,
                filename=h.filename,
                location=h.location,
                snippet=snippet,
                dense_score=round(h.dense_score, 4) if h.dense_score is not None else None,
                bm25_score=round(h.bm25_score, 4) if h.bm25_score is not None else None,
                rrf_score=round(h.rrf_score, 6),
                also_in=h.also_in,
            )
        )

    return SearchResponse(
        query=req.query,
        mode=req.mode,
        hits=hits_items,
        total_hits=len(hits_items),
        refused=ret_res.refused,
        refusal_reason=ret_res.refusal_reason,
        timing=ret_res.timing,
    )
