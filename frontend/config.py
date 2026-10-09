"""Konfigurasi frontend Streamlit untuk Personal Document Assistant."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class FrontendConfig:
    """Pengaturan konfigurasi antarmuka pengguna Streamlit."""

    backend_api_url: str = os.getenv(
        "PDA_API_URL",
        f"http://127.0.0.1:{os.getenv('API_PORT', '8001')}/api/v1",
    )
    api_key: str = os.getenv("PDA_API_KEY", os.getenv("API_KEY", ""))
    timeout_seconds: float = float(os.getenv("PDA_TIMEOUT", "300.0"))
    poll_interval_sec: float = float(os.getenv("PDA_POLL_INTERVAL", "2.0"))
    page_title: str = "Personal Document Assistant"
    default_top_k: int = 4
    max_top_k: int = 10


config = FrontendConfig()
