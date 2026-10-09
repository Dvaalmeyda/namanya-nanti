"""Komponen panel samping (sidebar) untuk kontrol filter dan parameter."""

from typing import Optional
import streamlit as st
from frontend.config import config
from frontend.state.chat_state import clear_chat_history


def render_sidebar(available_folders: Optional[list[str]] = None) -> dict[str, any]:
    """Merender kontrol pengaturan pencarian, filter metadata, dan tombol reset."""
    with st.sidebar:
        st.subheader("Pengaturan Sesi")

        # Mode streaming toggle
        streaming = st.toggle(
            "Mode Streaming (SSE)",
            value=st.session_state.get("streaming_mode", True),
            help="Menampilkan respons kata demi kata secara real-time.",
        )
        st.session_state["streaming_mode"] = streaming

        # Nilai TOP_K
        top_k = st.slider(
            "Batas Potongan Dokumen (TOP_K)",
            min_value=1,
            max_value=config.max_top_k,
            value=st.session_state.get("top_k", config.default_top_k),
            help="Jumlah potongan teks teratas yang dilampirkan ke prompt.",
        )
        st.session_state["top_k"] = top_k

        st.divider()
        st.subheader("Filter Dokumen")

        # Filter folder
        folder_options = sorted(list(set(available_folders or [])))
        selected_folders = st.multiselect(
            "Filter Folder",
            options=folder_options,
            default=st.session_state.get("selected_folders", []),
            help="Batasi pencarian hanya pada direktori tertentu.",
        )
        st.session_state["selected_folders"] = selected_folders

        # Filter tipe berkas
        type_options = ["pdf", "docx", "xlsx", "md", "txt"]
        selected_types = st.multiselect(
            "Filter Tipe Berkas",
            options=type_options,
            default=st.session_state.get("selected_file_types", []),
            help="Batasi pencarian pada format berkas tertentu.",
        )
        st.session_state["selected_file_types"] = selected_types

        st.divider()

        # Tombol bersihkan chat
        if st.button("Hapus Riwayat Percakapan", use_container_width=True):
            clear_chat_history()
            st.rerun()

        st.caption(f"Backend API: `{config.backend_api_url}`")

    return {
        "streaming": streaming,
        "top_k": top_k,
        "folders": selected_folders,
        "file_types": selected_types,
    }
