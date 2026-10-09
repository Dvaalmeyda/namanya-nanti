"""Entrypoint utama aplikasi Streamlit untuk Personal Document Assistant."""

import sys
from pathlib import Path

# Pastikan direktori root proyek terdaftar di sys.path saat dijalankan via streamlit run
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from frontend.client.document_client import DocumentClient
from frontend.client.system_client import SystemClient
from frontend.components.header import render_header
from frontend.components.sidebar import render_sidebar
from frontend.config import config
from frontend.state.session import init_session_state
from frontend.views.chat_view import render_chat_view
from frontend.views.documents_view import render_documents_view
from frontend.views.search_view import render_search_view
from frontend.views.system_view import render_system_view


def main() -> None:
    """Menginisialisasi layout utama dan navigasi antarmuka Streamlit."""
    st.set_page_config(
        page_title=config.page_title,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inisialisasi session state
    init_session_state()

    # Ambil data kesehatan dan daftar folder dokumen untuk sidebar
    sys_client = SystemClient()
    doc_client = DocumentClient()

    health_data = None
    available_folders = []

    try:
        health_data = sys_client.get_health()
        docs = doc_client.get_documents()
        for d in docs:
            rel_path = d.get("rel_path", "")
            if "/" in rel_path:
                folder = rel_path.split("/")[0]
                if folder not in available_folders:
                    available_folders.append(folder)
    except Exception:
        pass

    # Render Header dan Sidebar
    render_header(health_data=health_data)
    render_sidebar(available_folders=available_folders)

    # Navigasi Tampilan Utama (Tabs)
    tab_chat, tab_search, tab_docs, tab_sys = st.tabs([
        "Chat Asisten",
        "Laboratorium Retrieval",
        "Manajemen Dokumen",
        "Status Sistem",
    ])

    with tab_chat:
        render_chat_view()

    with tab_search:
        render_search_view()

    with tab_docs:
        render_documents_view()

    with tab_sys:
        render_system_view()


if __name__ == "__main__":
    main()
