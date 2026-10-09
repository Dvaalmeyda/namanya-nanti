"""Fungsi pembantu pemformatan angka, latensi, ukuran berkas, dan status."""

from datetime import datetime
from typing import Optional


def format_ms(val_ms: Optional[float]) -> str:
    """Memformat durasi waktu dari milidetik ke representasi ms atau detik."""
    if val_ms is None:
        return "-"
    if val_ms >= 1000.0:
        return f"{val_ms / 1000.0:.2f} s"
    return f"{val_ms:.1f} ms"


def format_bytes(size_bytes: Optional[int]) -> str:
    """Memformat ukuran byte ke satuan B, KB, MB, atau GB."""
    if size_bytes is None:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_speed(tok_s: Optional[float]) -> str:
    """Memformat kecepatan inferensi token per detik."""
    if tok_s is None or tok_s <= 0.0:
        return "-"
    return f"{tok_s:.1f} tok/s"


def format_datetime(dt_str: Optional[str]) -> str:
    """Memformat tanggal waktu ISO ke format yang mudah dibaca."""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str


def format_badge(status: str) -> str:
    """Mengembalikan label teks status standar tanpa emotikon."""
    status_clean = status.strip().upper()
    valid_badges = {
        "OK": "[OK]",
        "HEALTHY": "[SEHAT]",
        "RUNNING": "[RUNNING]",
        "IDLE": "[IDLE]",
        "COMPLETED": "[SELESAI]",
        "FAILED": "[GAGAL]",
        "ERROR": "[ERROR]",
        "DIRUJUK": "[DIRUJUK]",
        "TIDAK DIRUJUK": "[TIDAK DIRUJUK]",
        "LOLOS": "[LOLOS]",
        "DITOLAK": "[DITOLAK]",
    }
    return valid_badges.get(status_clean, f"[{status_clean}]")
