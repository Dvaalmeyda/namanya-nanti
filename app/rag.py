"""Mesin tanya-jawab RAG (Retrieval-Augmented Generation) lokal.

Mendukung eksekusi non-streaming (answer) dan streaming (answer_stream),
pemetaan sitasi nomor terverifikasi, dan isolasi gerbang penolakan.
"""

import logging
import re
import time
from typing import Any, Callable, Generator, Optional

from pydantic import BaseModel, Field

from app import ollama_client
from app.config import Settings, get_settings
from app.prompts import REFUSAL_TEXT, build_messages
from app.retrieval import Filters, Hit, retrieve

logger = logging.getLogger(__name__)


class Source(BaseModel):
    """Sumber rujukan potongan dokumen yang disertakan pada jawaban."""

    n: int
    doc_id: str
    chunk_id: str
    filename: str
    rel_path: str
    location: str
    also_in: list[str] = Field(default_factory=list)
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rrf_score: float = 0.0
    cited: bool = False


class RagResult(BaseModel):
    """Hasil jawaban lengkap RAG beserta daftar sumber, status penolakan, dan profil latensi."""

    answer: str
    sources: list[Source] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: Optional[str] = None
    timing: dict[str, Any] = Field(default_factory=dict)


def build_retrieval_query(
    question: str,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """Menggabungkan pertanyaan saat ini dengan riwayat pertanyaan user sebelumnya jika ada."""
    q_clean = question.strip()
    if not history:
        return q_clean

    past_user_qs = [
        m.get("content", "").strip()
        for m in history
        if m.get("role") == "user" and m.get("content", "").strip()
    ]
    if not past_user_qs:
        return q_clean

    # Sertakan pertanyaan pengguna terakhir untuk melengkapi konteks retrieval
    return f"{q_clean} {past_user_qs[-1]}"


def parse_citations(answer: str, max_n: int) -> set[int]:
    """Mengekstrak nomor sitasi [1], [2] yang sah dari teks jawaban."""
    found: set[int] = set()
    for m in re.finditer(r"\[(\d+(?:\s*,\s*\d+)*)\]", answer):
        raw = m.group(1)
        for part in raw.split(","):
            try:
                val = int(part.strip())
                if 1 <= val <= max_n:
                    found.add(val)
            except ValueError:
                pass
    return found


def _hits_to_sources(hits: list[Hit], cited_numbers: set[int]) -> list[Source]:
    """Mengonversi daftar Hit menjadi daftar Source dengan penanda status cited."""
    sources: list[Source] = []
    for idx, h in enumerate(hits, start=1):
        sources.append(
            Source(
                n=idx,
                doc_id=h.doc_id,
                chunk_id=h.chunk_id,
                filename=h.filename,
                rel_path=h.rel_path,
                location=h.location,
                also_in=h.also_in,
                dense_score=h.dense_score,
                bm25_score=h.bm25_score,
                rrf_score=h.rrf_score,
                cited=(idx in cited_numbers),
            )
        )
    return sources


# ==============================================================================
# Non-Streaming Answer
# ==============================================================================


def answer(
    question: str,
    history: Optional[list[dict[str, str]]] = None,
    filters: Optional[Filters] = None,
    mode: str = "hybrid",
    settings: Optional[Settings] = None,
    embed_fn: Optional[Callable[[list[str], str], list[list[float]]]] = None,
    chat_fn: Optional[Callable[..., Any]] = None,
) -> RagResult:
    """Menghasilkan jawaban RAG berbasis dokumen secara sinkron (non-streaming)."""
    t_total_0 = time.perf_counter()
    if settings is None:
        settings = get_settings()

    # 1. Bentuk kueri retrieval (gabung riwayat user jika ada)
    retrieval_query = build_retrieval_query(question, history)

    # 2. Retrieval potongan dokumen
    ret_res = retrieve(
        query=retrieval_query,
        filters=filters,
        mode=mode,
        settings=settings,
        embed_fn=embed_fn,
    )

    # 3. Cek Gerbang Penolakan Relevansi Rendah
    if ret_res.refused:
        total_ms = (time.perf_counter() - t_total_0) * 1000.0
        timing_info = {
            **ret_res.timing,
            "total_ms": round(total_ms, 2),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tokens_per_s": 0.0,
        }
        return RagResult(
            answer=REFUSAL_TEXT,
            sources=[],
            refused=True,
            refusal_reason=ret_res.refusal_reason,
            timing=timing_info,
        )

    # 4. Bangun pesan prompt terstruktur
    messages = build_messages(question, ret_res.hits, history=history, settings=settings)

    # 5. Inferensi LLM
    t_llm_0 = time.perf_counter()
    if chat_fn is not None:
        llm_resp = chat_fn(messages, stream=False)
    else:
        llm_resp = ollama_client.chat(messages, stream=False)

    answer_text = llm_resp.get("content", "").strip()

    # 6. Pascaproses Sitasi & Deteksi Penolakan Jawaban
    cited_nums = parse_citations(answer_text, max_n=len(ret_res.hits))
    sources = _hits_to_sources(ret_res.hits, cited_nums)

    is_refused = False
    refusal_reason = None
    if answer_text == REFUSAL_TEXT or answer_text.startswith(REFUSAL_TEXT):
        is_refused = True
        refusal_reason = "not_in_context"

    # 7. Pengumpulan Metrik & Profil Latensi
    prompt_tokens = llm_resp.get("prompt_eval_count", 0)
    prompt_duration_ns = llm_resp.get("prompt_eval_duration", 0)
    prefill_ms = prompt_duration_ns / 1e6 if prompt_duration_ns > 0 else 0.0

    completion_tokens = llm_resp.get("eval_count", 0)
    eval_duration_ns = llm_resp.get("eval_duration", 0)
    generate_ms = eval_duration_ns / 1e6 if eval_duration_ns > 0 else (time.perf_counter() - t_llm_0) * 1000.0

    tokens_per_s = (
        (completion_tokens / (generate_ms / 1000.0))
        if generate_ms > 0 and completion_tokens > 0
        else 0.0
    )

    total_ms = (time.perf_counter() - t_total_0) * 1000.0

    timing: dict[str, Any] = {
        "embed_ms": ret_res.timing.get("embed_ms", 0.0),
        "search_ms": ret_res.timing.get("search_ms", 0.0),
        "prefill_ms": round(prefill_ms, 2),
        "generate_ms": round(generate_ms, 2),
        "total_ms": round(total_ms, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens_per_s": round(tokens_per_s, 1),
    }

    return RagResult(
        answer=answer_text,
        sources=sources,
        refused=is_refused,
        refusal_reason=refusal_reason,
        timing=timing,
    )


# ==============================================================================
# Streaming Answer
# ==============================================================================


def answer_stream(
    question: str,
    history: Optional[list[dict[str, str]]] = None,
    filters: Optional[Filters] = None,
    mode: str = "hybrid",
    settings: Optional[Settings] = None,
    embed_fn: Optional[Callable[[list[str], str], list[list[float]]]] = None,
    chat_fn: Optional[Callable[..., Any]] = None,
) -> Generator[dict[str, Any], None, None]:
    """Menghasilkan jawaban RAG secara streaming token per token."""
    t_total_0 = time.perf_counter()
    if settings is None:
        settings = get_settings()

    # 1. Retrieval
    retrieval_query = build_retrieval_query(question, history)
    ret_res = retrieve(
        query=retrieval_query,
        filters=filters,
        mode=mode,
        settings=settings,
        embed_fn=embed_fn,
    )

    yield {"event": "retrieval", "hits_count": len(ret_res.hits), "timing": ret_res.timing}

    # 2. Cek Gerbang Penolakan
    if ret_res.refused:
        total_ms = (time.perf_counter() - t_total_0) * 1000.0
        yield {"event": "token", "content": REFUSAL_TEXT}
        yield {"event": "sources", "sources": []}
        yield {
            "event": "done",
            "refused": True,
            "refusal_reason": ret_res.refusal_reason,
            "timing": {
                **ret_res.timing,
                "total_ms": round(total_ms, 2),
                "tokens_per_s": 0.0,
            },
        }
        return

    # 3. Prompting
    messages = build_messages(question, ret_res.hits, history=history, settings=settings)

    t_llm_0 = time.perf_counter()
    full_answer_parts: list[str] = []
    first_token_time: Optional[float] = None

    last_metrics: dict[str, Any] = {}

    if chat_fn is not None:
        # Fallback jika chat_fn mock dipasang
        resp_obj = chat_fn(messages, stream=False)
        content_mock = resp_obj.get("content", "")
        yield {"event": "token", "content": content_mock}
        full_answer_parts.append(content_mock)
        last_metrics = resp_obj
    else:
        stream_generator = ollama_client.chat(messages, stream=True)
        for chunk in stream_generator:
            token = chunk.get("content", "")
            if token:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                full_answer_parts.append(token)
                yield {"event": "token", "content": token}

            if chunk.get("done", False):
                last_metrics = chunk

    full_answer = "".join(full_answer_parts).strip()

    # 4. Pascaproses Sitasi
    cited_nums = parse_citations(full_answer, max_n=len(ret_res.hits))
    sources = _hits_to_sources(ret_res.hits, cited_nums)

    is_refused = False
    refusal_reason = None
    if full_answer == REFUSAL_TEXT or full_answer.startswith(REFUSAL_TEXT):
        is_refused = True
        refusal_reason = "not_in_context"

    yield {"event": "sources", "sources": [s.model_dump() for s in sources]}

    # 5. Timing Metrik
    ttft_ms = (
        (first_token_time - t_llm_0) * 1000.0
        if first_token_time is not None
        else 0.0
    )

    prompt_tokens = last_metrics.get("prompt_eval_count", 0)
    prompt_duration_ns = last_metrics.get("prompt_eval_duration", 0)
    prefill_ms = prompt_duration_ns / 1e6 if prompt_duration_ns > 0 else 0.0

    completion_tokens = last_metrics.get("eval_count", 0)
    eval_duration_ns = last_metrics.get("eval_duration", 0)
    generate_ms = (
        eval_duration_ns / 1e6
        if eval_duration_ns > 0
        else (time.perf_counter() - (first_token_time or t_llm_0)) * 1000.0
    )

    tokens_per_s = (
        (completion_tokens / (generate_ms / 1000.0))
        if generate_ms > 0 and completion_tokens > 0
        else 0.0
    )

    total_ms = (time.perf_counter() - t_total_0) * 1000.0

    timing = {
        "embed_ms": ret_res.timing.get("embed_ms", 0.0),
        "search_ms": ret_res.timing.get("search_ms", 0.0),
        "ttft_ms": round(ttft_ms, 2),
        "prefill_ms": round(prefill_ms, 2),
        "generate_ms": round(generate_ms, 2),
        "total_ms": round(total_ms, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens_per_s": round(tokens_per_s, 1),
    }

    yield {
        "event": "done",
        "refused": is_refused,
        "refusal_reason": refusal_reason,
        "timing": timing,
    }
