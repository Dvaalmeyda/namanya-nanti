import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.config import get_settings

SENSITIVE_FIELDS = {
    "text",
    "question",
    "answer",
    "context",
    "chunk_text",
    "prompt",
}


class RedactionFilter(logging.Filter):
    """Filter untuk menyensor field teks dokumen dan pertanyaan jika LOG_CONTENT=False."""

    def filter(self, record: logging.LogRecord) -> bool:
        settings = get_settings()
        if settings.LOG_CONTENT:
            return True

        # Sensor atribut khusus pada record
        for field in SENSITIVE_FIELDS:
            if hasattr(record, field):
                setattr(record, field, "[REDACTED]")

        # Jika record memiliki atribut 'extra' atau dict context dalam args
        if isinstance(record.args, dict):
            sanitized_args = dict(record.args)
            for k in sanitized_args:
                if k in SENSITIVE_FIELDS:
                    sanitized_args[k] = "[REDACTED]"
            record.args = sanitized_args

        return True


def setup_logging() -> logging.Logger:
    """Mengonfigurasi logging terstruktur ke console dan file index/app.log."""
    settings = get_settings()

    # Pastikan direktori index tersedia
    log_dir: Path = settings.INDEX_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    root_logger = logging.getLogger()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Hapus handler lama jika ada agar tidak terduplikasi
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    redaction_filter = RedactionFilter()

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redaction_filter)
    root_logger.addHandler(console_handler)

    # File Handler dengan rotasi 5MB, 3 backup
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction_filter)
    root_logger.addHandler(file_handler)

    return logging.getLogger("personal_doc_assistant")
