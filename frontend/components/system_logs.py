"""Komponen konsol penampil log sistem backend waktu nyata."""

import streamlit as st
from frontend.client.system_client import SystemClient


def render_system_logs() -> None:
    """Merender antarmuka konsol log sistem backend terfilter."""
    st.subheader("Konsol Log Sistem Backend")
    st.caption("Membaca berkas log terproteksi (data/index/app.log) yang telah disanitasi.")

    col_lvl, col_lines, col_search, col_btn = st.columns([2, 2, 3, 1])

    with col_lvl:
        level = st.selectbox("Level Log", ["ALL", "INFO", "WARNING", "ERROR"], index=0)
    with col_lines:
        lines_count = st.selectbox("Jumlah Baris", [50, 100, 200, 500], index=1)
    with col_search:
        search_query = st.text_input("Cari Teks Log", value="", placeholder="kata kunci...")
    with col_btn:
        st.write("")
        st.write("")
        refresh = st.button("Muat Ulang")

    client = SystemClient()
    try:
        data = client.get_system_logs(lines=lines_count, level=level, search=search_query or None)
        logs = data.get("logs", [])
        total = data.get("total_lines", 0)

        st.caption(f"Menampilkan {total} baris log dari `{data.get('log_file', '-')}`:")
        if logs:
            log_text = "\n".join(logs)
            st.code(log_text, language="log")
        else:
            st.info("Tidak ada catatan log yang cocok dengan kriteria filter.")
    except Exception as exc:
        st.error(f"Gagal mengambil log dari backend: {exc}")
