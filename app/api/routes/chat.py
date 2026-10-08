"""Endpoint tanya-jawab RAG: respons JSON utuh (/chat) dan streaming SSE (/chat/stream)."""

import asyncio
import json
import logging
import sqlite3
import threading
from typing import Any, AsyncGenerator, Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_app_settings,
    get_chat_semaphore,
    get_db_conn,
    get_vector_index,
    verify_api_key,
)
from app.api.schemas import ChatRequest, ChatResponse, SourceItem
from app.config import Settings
from app import ollama_client
from app import rag
from app.retrieval import Filters
from app import store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"], dependencies=[Depends(verify_api_key)])


def _build_filters(req: ChatRequest) -> Optional[Filters]:
    """Membentuk objek Filters dari ChatRequest."""
    if not req.filters:
        return None
    return Filters(
        folders=req.filters.folders,
        file_types=req.filters.file_types,
        doc_ids=req.filters.doc_ids,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Tanya-jawab dokumen (JSON Utuh)",
    description="Endpoint utama untuk Swagger UI. Menghasilkan jawaban terstruktur, daftar sitasi sumber [1], [2], dan metrik latensi proses.",
)
async def chat_json(
    req: ChatRequest,
    settings: Settings = Depends(get_app_settings),
    semaphore: asyncio.Semaphore = Depends(get_chat_semaphore),
    conn: sqlite3.Connection = Depends(get_db_conn),
    vindex: store.VectorIndex = Depends(get_vector_index),
) -> ChatResponse:
    """Menghasilkan jawaban RAG sinkron dalam bentuk JSON utuh."""
    # 1. Antrean inferensi CPU via semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=10.0)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "chat_queue_full",
                "message": "Antrean inferensi CPU sedang penuh. Harap coba lagi beberapa saat lagi.",
                "detail": f"Batas konkurensi: {settings.MAX_CONCURRENT_CHAT} permintaan.",
            },
        )

    filters = _build_filters(req)
    history_dicts = [h.model_dump() for h in req.history] if req.history else None

    try:
        # Jalankan komputasi retrieval & inferensi LLM di worker threadpool
        def _run_answer() -> rag.RagResult:
            return rag.answer(
                question=req.question,
                history=history_dicts,
                filters=filters,
                settings=settings,
            )

        rag_res: rag.RagResult = await anyio.to_thread.run_sync(_run_answer)

    except ollama_client.OllamaUnavailable as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ollama_unavailable",
                "message": "Server Ollama lokal tidak dapat dihubungi.",
                "detail": str(err),
            },
        )
    except ollama_client.ModelNotFound as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "model_not_found",
                "message": "Model yang dikonfigurasi belum di-pull di Ollama.",
                "detail": str(err),
            },
        )
    except Exception as exc:
        logger.error("Terjadi kesalahan saat memproses chat: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "internal_error", "message": f"Kesalahan internal RAG: {exc}"},
        )
    finally:
        semaphore.release()

    # Bentuk respons SourceItem
    sources_items: list[SourceItem] = []
    for s in rag_res.sources:
        chunk_text = None
        if req.include_chunks:
            # Ambil teks chunk dari basis data jika diminta untuk inspeksi
            cur = conn.execute("SELECT text FROM chunks WHERE chunk_id = ?;", (s.chunk_id,))
            row = cur.fetchone()
            if row:
                chunk_text = row["text"]

        sources_items.append(
            SourceItem(
                n=s.n,
                doc_id=s.doc_id,
                chunk_id=s.chunk_id,
                filename=s.filename,
                rel_path=s.rel_path,
                location=s.location,
                also_in=s.also_in,
                dense_score=round(s.dense_score, 4) if s.dense_score is not None else None,
                bm25_score=round(s.bm25_score, 4) if s.bm25_score is not None else None,
                rrf_score=round(s.rrf_score, 6),
                cited=s.cited,
                text=chunk_text,
            )
        )

    return ChatResponse(
        answer=rag_res.answer,
        sources=sources_items,
        refused=rag_res.refused,
        refusal_reason=rag_res.refusal_reason,
        timing=rag_res.timing,
    )


@router.post(
    "/chat/stream",
    summary="Tanya-jawab dokumen secara streaming (Server-Sent Events)",
    description="Menghasilkan jawaban token demi token secara real-time melalui protokol SSE. Urutan event: token -> sources -> done (atau error).",
)
async def chat_stream(
    req: ChatRequest,
    settings: Settings = Depends(get_app_settings),
    semaphore: asyncio.Semaphore = Depends(get_chat_semaphore),
) -> StreamingResponse:
    """Menghasilkan jawaban streaming menggunakan Server-Sent Events (SSE)."""
    # 1. Antrean via semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=10.0)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "chat_queue_full",
                "message": "Antrean inferensi CPU sedang penuh. Coba lagi dalam beberapa saat.",
            },
        )

    filters = _build_filters(req)
    history_dicts = [h.model_dump() for h in req.history] if req.history else None

    async def _sse_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _worker() -> None:
            try:
                for event_dict in rag.answer_stream(
                    question=req.question,
                    history=history_dicts,
                    filters=filters,
                    settings=settings,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, event_dict)
            except ollama_client.OllamaUnavailable as err:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "event": "error",
                        "code": "ollama_unavailable",
                        "message": "Server Ollama lokal tidak dapat dihubungi.",
                        "detail": str(err),
                    },
                )
            except ollama_client.ModelNotFound as err:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "event": "error",
                        "code": "model_not_found",
                        "message": "Model Ollama belum di-pull.",
                        "detail": str(err),
                    },
                )
            except Exception as exc:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "event": "error",
                        "code": "internal_error",
                        "message": str(exc),
                    },
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        worker_thread = threading.Thread(target=_worker, daemon=True)
        worker_thread.start()

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break

                ev_name = item.get("event", "message")
                # Hanya kirim event publik yang relevan: token, sources, done, error
                if ev_name in ("token", "sources", "done", "error"):
                    payload = json.dumps(item, ensure_ascii=False)
                    yield f"event: {ev_name}\ndata: {payload}\n\n"
        finally:
            semaphore.release()

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
