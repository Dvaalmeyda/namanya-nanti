from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfigurasi terpusat sistem berbasis pydantic-settings."""

    # Ollama settings
    OLLAMA_HOST: str = "http://127.0.0.1:11434"
    OLLAMA_TIMEOUT_S: int = 300
    KEEP_ALIVE: str = "30m"
    NUM_THREAD: Optional[int] = None

    # LLM settings
    LLM_MODEL: str = "qwen3:4b-instruct"
    LLM_THINK: bool = False
    NUM_CTX: int = 4096
    NUM_PREDICT: int = 384
    TEMPERATURE: float = 0.1

    # Embedding settings
    EMBED_MODEL: str = "bge-m3"
    EMBED_QUERY_PREFIX: str = ""
    EMBED_DOC_PREFIX: str = ""
    EMBED_BATCH: int = 16

    # Loader settings
    PDF_BACKEND: str = "pymupdf"
    OCR_MIN_CHARS: int = 50
    MAX_FILE_MB: int = 50
    XLSX_ROW_CHUNK: int = 30

    # Indexing & Storage settings
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100
    VECTOR_DTYPE: str = "float32"
    STEMMER: str = "none"

    # Retrieval & RAG settings
    TOP_K: int = 4
    CANDIDATES: int = 20
    RRF_K: int = 60
    MIN_DENSE_SCORE: float = 0.35
    MIN_BM25_SCORE: float = 0.0
    MAX_CONTEXT_CHARS: int = 4000
    HISTORY_TURNS: int = 3
    HISTORY_MAX_CHARS: int = 1500
    QUERY_REWRITE: bool = False

    # Paths
    DOCS_DIR: Path = Path("data/docs")
    SAMPLE_DIR: Path = Path("data/sample")
    INDEX_DIR: Path = Path("data/index")

    # Privacy & Logging
    ALLOW_REMOTE: bool = False
    LOG_CONTENT: bool = False
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Mengembalikan instance singleton Settings dengan cache."""
    return Settings()
