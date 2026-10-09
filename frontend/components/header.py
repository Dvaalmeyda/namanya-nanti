"""Komponen baris atas (header) aplikasi dan status backend."""

from typing import Any, Optional
import streamlit as st
from frontend.utils.formatters import format_badge


def render_header(health_data: Optional[dict[str, Any]] = None) -> None:
    """Merender header aplikasi, deskripsi sistem, dan badge status backend."""
    col_title, col_status = st.columns([3, 1])

    with col_title:
        st.title("Personal Document Assistant")
        st.caption("Asisten tanya-jawab dokumen pribadi berbasis Retrieval-Augmented Generation (RAG) lokal.")

    with col_status:
        if health_data and health_data.get("status") == "ok":
            st.success(f"Status Sistem: {format_badge('OK')}")
            cfg = health_data.get("config_summary", {})
            st.caption(f"Model: `{cfg.get('llm_model', '-')}`")
            st.caption(f"Dokumen: {health_data.get('document_count', 0)} ({health_data.get('chunk_count', 0)} chunk)")
        elif health_data and health_data.get("status") == "degraded":
            st.warning(f"Status Sistem: {format_badge('DEGRADED')}")
            st.caption("Ollama atau indeks memerlukan perhatian.")
        else:
            st.error(f"Status Sistem: {format_badge('ERROR')}")
            st.caption("Backend tidak terhubung di loopback.")

    st.divider()
