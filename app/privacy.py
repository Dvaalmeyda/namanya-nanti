import os
from urllib.parse import urlparse

from app.config import get_settings

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def apply_offline_env() -> None:
    """Mengaktifkan flag lingkungan offline untuk mencegah telemetri atau unduhan pihak ketiga."""
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def assert_local_only(url: str) -> None:
    """Memastikan URL mengarah ke loopback host (127.0.0.1/localhost/::1) kecuali ALLOW_REMOTE=True."""
    settings = get_settings()
    if settings.ALLOW_REMOTE:
        return

    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        raise ValueError(f"URL tidak valid atau tidak memiliki host: {url}")

    if hostname.lower() not in LOOPBACK_HOSTS:
        raise ValueError(
            f"Akses ke host non-loopback '{hostname}' ditolak demi privasi. "
            "Ubah ALLOW_REMOTE=true di konfigurasi jika akses remote ini disengaja."
        )
