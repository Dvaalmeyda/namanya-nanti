"""Aplikasi utama FastAPI untuk Asisten Dokumen Pribadi Lokal.

Menyediakan pabrik create_app(), penanganan siklus hidup (lifespan),
middleware pencatatan log tanpa kebocoran konten privasi, dan exception handlers terpusat.
"""

from contextlib import asynccontextmanager
import logging
import threading
import time
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.deps import get_job_manager
from app.api.routes import chat, documents, health, index, search
from app.api.schemas import ErrorResponse
from app.config import Settings, get_settings
from app.logging_setup import setup_logging
from app import ollama_client
from app.privacy import apply_offline_env, assert_local_only
from app import store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manajer siklus hidup aplikasi (startup dan shutdown)."""
    settings = getattr(app.state, "settings", None) or get_settings()

    # 1. Terapkan flag lingkungan offline dan pastikan host lokal
    apply_offline_env()
    assert_local_only(settings.OLLAMA_HOST)

    # 2. Inisialisasi basis data SQLite dan muat VectorIndex ke RAM
    db_path = settings.INDEX_DIR / "index.db"
    store.init_db(db_path)

    vector_index = store.VectorIndex(dtype=settings.VECTOR_DTYPE)
    conn = store.get_connection(db_path)
    vector_index.load_from_db(conn)
    conn.close()

    app.state.vector_index = vector_index
    app.state.job_manager = get_job_manager()

    logger.info(
        "Basis data dan VectorIndex siap (indeks versi: %s, matriks: %s)",
        vector_index.cached_version,
        "terisi" if not vector_index.is_empty() else "kosong",
    )

    # 3. Warm-up model di thread latar belakang jika dikonfigurasi
    if settings.WARMUP:
        def _bg_warmup() -> None:
            logger.info("Memulai pemanasan model awal (warmup)...")
            res = ollama_client.warmup()
            logger.info("Warmup selesai: %s", res)

        threading.Thread(target=_bg_warmup, daemon=True, name="bg-warmup").start()

    yield

    # Shutdown: penutupan tertib
    logger.info("Menutup layanan API Asisten Dokumen Pribadi...")


def create_app(settings: Settings = None) -> FastAPI:
    """Pabrik pembuatan instance aplikasi FastAPI."""
    setup_logging()
    app_settings = settings or get_settings()

    app = FastAPI(
        title="Personal Document Assistant API",
        description=(
            "REST API lokal dan offline untuk tanya-jawab dokumen pribadi (PDF, DOCX, XLSX, MD, TXT) "
            "menggunakan model Ollama lokal dan penyimpanan SQLite/NumPy."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    # ==========================================================================
    # Middleware Logging Permintaan
    # ==========================================================================
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        dur_ms = (time.perf_counter() - t0) * 1000.0
        content_len = response.headers.get("content-length", "-")

        logger.info(
            "%s %s -> %d (%.1fms, %s bytes)",
            request.method,
            request.url.path,
            response.status_code,
            dur_ms,
            content_len,
        )
        return response

    # ==========================================================================
    # Penanganan Kesalahan Global (Exception Handlers)
    # ==========================================================================
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail_data = exc.detail
        if isinstance(detail_data, dict):
            code = detail_data.get("code", "http_error")
            message = detail_data.get("message", str(exc.detail))
            detail = detail_data.get("detail")
        else:
            code = f"error_{exc.status_code}"
            message = str(detail_data)
            detail = None

        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(code=code, message=message, detail=detail).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                code="validation_error",
                message="Data permintaan tidak valid atau tidak memenuhi skema.",
                detail=exc.errors(),
            ).model_dump(),
        )

    @app.exception_handler(ollama_client.OllamaUnavailable)
    async def ollama_unavailable_handler(request: Request, exc: ollama_client.OllamaUnavailable):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                code="ollama_unavailable",
                message="Layanan Ollama lokal tidak dapat dihubungi.",
                detail=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(ollama_client.ModelNotFound)
    async def model_not_found_handler(request: Request, exc: ollama_client.ModelNotFound):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                code="model_not_found",
                message="Model Ollama yang diminta belum diunduh.",
                detail=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("Terjadi unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                code="internal_server_error",
                message="Terjadi kesalahan internal pada server.",
                detail=str(exc),
            ).model_dump(),
        )

    # ==========================================================================
    # Registrasi Router dengan Prefix /api/v1
    # ==========================================================================
    api_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(chat.router, prefix=api_prefix)
    app.include_router(search.router, prefix=api_prefix)
    app.include_router(documents.router, prefix=api_prefix)
    app.include_router(index.router, prefix=api_prefix)

    return app


# Instance app default untuk Uvicorn
app = create_app()
