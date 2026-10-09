"""Komponen visualisasi metrik latensi dan profil eksekusi."""

from typing import Any, Optional
import streamlit as st
from frontend.utils.formatters import format_ms, format_speed


def render_metrics_cards(timing: Optional[dict[str, Any]] = None) -> None:
    """Merender kartu ringkasan metrik waktu proses per tahap."""
    if not timing:
        return

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Embedding", format_ms(timing.get("embed_ms")))
    with col2:
        st.metric("Retrieval", format_ms(timing.get("search_ms")))
    with col3:
        st.metric("TTFT", format_ms(timing.get("ttft_ms")))
    with col4:
        st.metric("Kecepatan", format_speed(timing.get("tokens_per_s")))
    with col5:
        st.metric("Total Waktu", format_ms(timing.get("total_ms")))
