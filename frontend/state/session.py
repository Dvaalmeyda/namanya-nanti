"""Inisialisasi dan akses terstruktur session state Streamlit."""

from typing import Any
import streamlit as st
from frontend.config import config


def init_session_state() -> None:
    """Menginisialisasi seluruh variabel session state yang dibutuhkan aplikasi."""
    defaults: dict[str, Any] = {
        "messages": [],
        "streaming_mode": True,
        "selected_folders": [],
        "selected_file_types": [],
        "top_k": config.default_top_k,
        "backend_health": None,
        "active_tab": "Chat Asisten",
        "inspection_chunk": None,
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get_state(key: str, default: Any = None) -> Any:
    """Mengambil nilai dari session state dengan fallback nilai bawaan."""
    return st.session_state.get(key, default)


def set_state(key: str, value: Any) -> None:
    """Menyimpan nilai ke session state."""
    st.session_state[key] = value
