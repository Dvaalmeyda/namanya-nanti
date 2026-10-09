# ==============================================================================
# Tahap 1: Base - Lingkungan dasar Python 3.11-slim
# ==============================================================================
FROM python:3.11-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /uvx /bin/

# ==============================================================================
# Tahap 2: Builder - Instalasi dependensi menggunakan uv
# ==============================================================================
FROM base AS builder

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ==============================================================================
# Tahap 3: Runtime - Pengguna non-root dan kode aplikasi
# ==============================================================================
FROM base AS runtime

RUN groupadd -r appgroup && useradd -r -g appgroup -u 1000 appuser

# Salin lingkungan virtual dari builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Siapkan direktori penyimpanan data
RUN mkdir -p /app/data/docs /app/data/index /app/data/sample \
    && chown -R appuser:appgroup /app

# Salin kode aplikasi
COPY --chown=appuser:appgroup app/ /app/app/
COPY --chown=appuser:appgroup frontend/ /app/frontend/
COPY --chown=appuser:appgroup data/sample/ /app/data/sample/
COPY --chown=appuser:appgroup pyproject.toml /app/pyproject.toml

USER appuser

# ==============================================================================
# Tahap 4: Target Backend (FastAPI)
# ==============================================================================
FROM runtime AS backend

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# ==============================================================================
# Tahap 5: Target Frontend (Streamlit)
# ==============================================================================
FROM runtime AS frontend

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "frontend/app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true", \
     "--browser.gatherUsageStats", "false"]
