"""Endpoint pemeriksaan kesehatan sistem dan status komponen (Health Check)."""

import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_app_settings
from app.api.schemas import HealthResponse, SystemLogsResponse
from app.config import Settings
from app import ollama_client
from app import store

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Pemeriksaan status kesehatan sistem dan komponen",
    description="Memeriksa konektivitas Ollama, model yang termuat, jumlah dokumen terindeks, dan versi basis data. Tidak memerlukan autentikasi.",
)
def get_health(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    """Mengembalikan status kesehatan sistem secara menyeluruh."""
    db_path = settings.INDEX_DIR / "index.db"

    # 1. Periksa basis data SQLite
    doc_count = 0
    chunk_count = 0
    index_version = "0"

    if db_path.exists():
        try:
            conn = store.get_connection(db_path)
            cur = conn.execute("SELECT count(*) AS total FROM documents;")
            doc_count = cur.fetchone()["total"]

            cur = conn.execute("SELECT count(*) AS total FROM chunks;")
            chunk_count = cur.fetchone()["total"]

            index_version = store.get_setting(conn, "index_version") or "0"
            conn.close()
        except Exception:
            pass

    # 2. Periksa server Ollama
    ollama_connected = False
    available_models: list[str] = []
    loaded_models: list[dict[str, Any]] = []

    try:
        available_models = ollama_client.list_models()
        ollama_connected = True
        loaded_models = ollama_client.loaded_models()
    except Exception:
        ollama_connected = False

    overall_status = "ok" if (ollama_connected and db_path.exists()) else "degraded"

    config_summary = {
        "llm_model": settings.LLM_MODEL,
        "embed_model": settings.EMBED_MODEL,
        "top_k": settings.TOP_K,
        "num_ctx": settings.NUM_CTX,
        "max_concurrent_chat": settings.MAX_CONCURRENT_CHAT,
    }

    return HealthResponse(
        status=overall_status,
        ollama_connected=ollama_connected,
        models_available=available_models,
        models_loaded=loaded_models,
        document_count=doc_count,
        chunk_count=chunk_count,
        index_version=index_version,
        config_summary=config_summary,
    )


@router.get(
    "/system/logs",
    response_model=SystemLogsResponse,
    summary="Mengambil baris log sistem backend",
    description="Membaca log dari berkas app.log yang telah disanitasi oleh RedactionFilter. Mendukung filter baris, level, dan pencarian teks.",
)
def get_system_logs(
    lines: int = Query(100, ge=1, le=1000, description="Jumlah baris terakhir yang diambil"),
    level: Optional[str] = Query(None, description="Filter level log (DEBUG, INFO, WARNING, ERROR)"),
    search: Optional[str] = Query(None, description="Pencarian kata kunci teks dalam log"),
    settings: Settings = Depends(get_app_settings),
) -> SystemLogsResponse:
    """Mengembalikan baris log backend terfilter."""
    log_file = settings.INDEX_DIR / "app.log"
    if not log_file.exists():
        return SystemLogsResponse(
            log_file=str(log_file),
            total_lines=0,
            logs=[],
        )

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = [line.rstrip("\r\n") for line in f if line.strip()]
    except Exception:
        all_lines = []

    # Terapkan filter level jika ada
    filtered = all_lines
    if level:
        lvl_tag = f"| {level.strip().upper()}"
        filtered = [l for l in filtered if lvl_tag in l]

    # Terapkan filter pencarian teks jika ada
    if search:
        search_lower = search.strip().lower()
        filtered = [l for l in filtered if search_lower in l.lower()]

    # Ambil baris terakhir sejumlah 'lines'
    tail_lines = filtered[-lines:] if len(filtered) > lines else filtered

    return SystemLogsResponse(
        log_file=str(log_file),
        total_lines=len(tail_lines),
        logs=tail_lines,
    )

