"""Dependency injection untuk endpoint FastAPI.

Menyediakan akses ke Settings, koneksi SQLite, VectorIndex, autentikasi X-API-Key,
dan Semaphore antrean chat inferensi CPU.
"""

import asyncio
from collections.abc import Generator
import logging
import secrets
import sqlite3
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.api.jobs import IndexingJobManager, get_job_manager
from app.config import Settings, get_settings
from app import store

logger = logging.getLogger(__name__)

# Skema keamanan header API Key untuk Swagger UI
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_app_settings() -> Settings:
    """Dependency untuk mendapatkan konfigurasi sistem."""
    return get_settings()


def get_db_conn(settings: Settings = Depends(get_app_settings)) -> Generator[sqlite3.Connection, None, None]:
    """Dependency untuk mendapatkan koneksi SQLite terisolasi per request."""
    db_path = settings.INDEX_DIR / "index.db"
    conn = store.get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_vector_index(request: Request) -> store.VectorIndex:
    """Dependency untuk mengakses instance singleton VectorIndex dari app.state."""
    vindex = getattr(request.app.state, "vector_index", None)
    if vindex is None:
        settings = get_settings()
        vindex = store.VectorIndex(dtype=settings.VECTOR_DTYPE)
        db_path = settings.INDEX_DIR / "index.db"
        if db_path.exists():
            conn = store.get_connection(db_path)
            vindex.load_from_db(conn)
            conn.close()
        request.app.state.vector_index = vindex
    return vindex


def get_chat_semaphore(request: Request) -> asyncio.Semaphore:
    """Dependency untuk mendapatkan Semaphore pembatas konkurensi chat CPU."""
    sem = getattr(request.app.state, "chat_semaphore", None)
    if sem is None:
        settings = get_settings()
        sem = asyncio.Semaphore(max(1, settings.MAX_CONCURRENT_CHAT))
        request.app.state.chat_semaphore = sem
    return sem


def verify_api_key(
    key: Optional[str] = Security(api_key_header),
    settings: Settings = Depends(get_app_settings),
) -> Optional[str]:
    """Memvalidasi API key bila diaktifkan pada konfigurasi.
    
    Bila API_KEY kosong di .env, verifikasi dilewati (terbuka).
    Bila terisi, header X-API-Key wajib disertakan dan dicocokkan via compare_digest.
    """
    configured_key = settings.API_KEY.strip()
    if not configured_key:
        return None

    if not key or not secrets.compare_digest(key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "unauthorized",
                "message": "Autentikasi gagal. API key tidak valid atau tidak disertakan.",
                "detail": "Kirimkan header 'X-API-Key' yang sesuai.",
            },
        )
    return key
