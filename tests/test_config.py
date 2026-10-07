from pathlib import Path
from app.config import Settings, get_settings


def test_default_settings():
    """Memastikan nilai default konfigurasi sesuai spesifikasi Fase 0."""
    settings = Settings(_env_file=None)
    assert settings.OLLAMA_HOST == "http://127.0.0.1:11434"
    assert settings.LLM_MODEL == "qwen3:4b-instruct"
    assert settings.LLM_THINK is False
    assert settings.NUM_CTX == 4096
    assert settings.NUM_PREDICT == 384
    assert settings.EMBED_MODEL == "bge-m3"
    assert settings.ALLOW_REMOTE is False
    assert settings.LOG_CONTENT is False
    assert settings.DOCS_DIR == Path("data/docs")
    assert settings.SAMPLE_DIR == Path("data/sample")


def test_settings_override(monkeypatch):
    """Memastikan override environment variable berfungsi."""
    monkeypatch.setenv("LLM_MODEL", "qwen3.5:4b")
    monkeypatch.setenv("ALLOW_REMOTE", "true")
    monkeypatch.setenv("NUM_PREDICT", "512")

    settings = Settings(_env_file=None)
    assert settings.LLM_MODEL == "qwen3.5:4b"
    assert settings.ALLOW_REMOTE is True
    assert settings.NUM_PREDICT == 512
