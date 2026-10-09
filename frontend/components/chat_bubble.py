"""Komponen render balon percakapan pengguna dan asisten beserta sitasi dan trace."""

from typing import Any
import streamlit as st
from frontend.components.citation_viewer import render_citations
from frontend.components.metrics_display import render_metrics_cards
from frontend.components.workflow_trace import render_workflow_trace


def render_chat_message(msg: dict[str, Any], index: int) -> None:
    """Merender satu balon pesan (user atau assistant) beserta komponen pelengkapnya."""
    role = msg.get("role", "user")
    content = msg.get("content", "")

    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
        return

    with st.chat_message("assistant"):
        st.markdown(content)

        # Status jika ditolak
        if msg.get("refused"):
            reason = msg.get("refusal_reason", "low_relevance")
            if reason == "low_relevance":
                st.info("Pertanyaan ditolak oleh gerbang relevansi karena tidak berhubungan dengan isi dokumen.")
            elif reason == "not_in_context":
                st.info("Informasi pertanyaan tidak ditemukan dalam dokumen acuan.")

        # Tampilkan sitasi
        sources = msg.get("sources", [])
        if sources:
            render_citations(sources)

        # Tampilkan ringkasan metrik
        timing = msg.get("timing", {})
        if timing:
            render_metrics_cards(timing)

        # Tampilkan alur kerja (workflow trace)
        trace = msg.get("workflow_trace", {})
        if trace:
            render_workflow_trace(trace, key_suffix=f"msg_{index}")
