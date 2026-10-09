"""Tampilan status sistem, informasi model Ollama, dan konsol log (System View)."""

import streamlit as st
from frontend.client.system_client import SystemClient
from frontend.components.system_logs import render_system_logs
from frontend.utils.formatters import format_badge


def render_system_view() -> None:
    """Merender tab diagnostik kesehatan backend dan konsol log real-time."""
    tab_diag, tab_logs = st.tabs(["Kesehatan Sistem & Model", "Konsol Log Sistem"])

    with tab_diag:
        _render_diagnostics()

    with tab_logs:
        render_system_logs()


def _render_diagnostics() -> None:
    """Merender metrik kesehatan backend dan daftar model Ollama."""
    st.subheader("Diagnostik Layanan Lokal")
    client = SystemClient()

    try:
        health = client.get_health()
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Status Backend", format_badge(health.get("status", "-")))
            ollama_status = "OK" if health.get("ollama_connected") else "ERROR"
            st.metric("Koneksi Ollama", format_badge(ollama_status))

        with col2:
            st.metric("Total Dokumen", health.get("document_count", 0))
            st.metric("Total Chunks", health.get("chunk_count", 0))

        with col3:
            st.metric("Versi Indeks", f"v{health.get('index_version', '-')}")

        st.divider()
        col_m1, col_m2 = st.columns(2)

        with col_m1:
            st.markdown("**Model yang Tersedia di Ollama:**")
            avail = health.get("models_available", [])
            if avail:
                for m in avail:
                    st.code(m, language="text")
            else:
                st.info("Tidak ada model yang terdeteksi.")

        with col_m2:
            st.markdown("**Model yang Aktif di RAM / VRAM:**")
            loaded = health.get("models_loaded", [])
            if loaded:
                for lm in loaded:
                    st.code(lm.get("name", str(lm)), language="text")
            else:
                st.caption("Belum ada model yang termuat di memori.")

        st.divider()
        st.markdown("**Ringkasan Konfigurasi Aktif:**")
        st.json(health.get("config_summary", {}))

    except Exception as exc:
        st.error(f"Gagal mengambil status sistem: {exc}")
