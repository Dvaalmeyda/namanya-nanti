"""Tampilan laboratorium pengujian retrieval murni (Search View)."""

import pandas as pd
import streamlit as st
from frontend.client.search_client import SearchClient
from frontend.utils.formatters import format_ms


def render_search_view() -> None:
    """Merender antarmuka perbandingan metode pencarian retrieval dokumen."""
    st.subheader("Laboratorium Retrieval Dokumen")
    st.caption("Menguji pencarian potongan dokumen secara langsung tanpa inferensi LLM.")

    col_q, col_mode, col_k = st.columns([4, 2, 1])
    with col_q:
        query_text = st.text_input("Kueri Pencarian", placeholder="masukkan kata kunci atau pertanyaan...")
    with col_mode:
        mode = st.selectbox("Mode Retrieval", ["hybrid", "dense", "bm25"], index=0)
    with col_k:
        top_k = st.number_input("Top K", min_value=1, max_value=20, value=5)

    folders = st.session_state.get("selected_folders") or None
    file_types = st.session_state.get("selected_file_types") or None

    if st.button("Jalankan Pencarian", disabled=not bool(query_text.strip())):
        client = SearchClient()
        with st.spinner("Mengeksekusi retrieval..."):
            try:
                res = client.search(
                    query=query_text.strip(),
                    mode=mode,
                    top_k=top_k,
                    folders=folders,
                    file_types=file_types,
                )
                _display_search_results(res)
            except Exception as exc:
                st.error(f"Pencarian gagal: {exc}")


def _display_search_results(res: dict) -> None:
    """Menampilkan tabel dan metrik hasil pencarian retrieval."""
    hits = res.get("hits", [])
    timing = res.get("timing", {})

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Total Ditemukan", f"{res.get('total_hits', len(hits))} potongan")
    with col_m2:
        st.metric("Durasi Embedding", format_ms(timing.get("embed_ms")))
    with col_m3:
        st.metric("Durasi Retrieval", format_ms(timing.get("search_ms")))

    if not hits:
        st.info("Tidak ada potongan dokumen yang memenuhi kriteria pencarian.")
        return

    table_data = []
    for h in hits:
        table_data.append({
            "Peringkat": h.get("rank", 1),
            "Dokumen": h.get("filename", "-"),
            "Lokasi": h.get("location", "-"),
            "Cuplikan Teks": h.get("text_preview", "-")[:120] + "...",
            "Skor Akhir": f"{h.get('score', 0.0):.5f}",
            "Dense": f"{h.get('dense_score', 0.0):.4f}" if h.get("dense_score") is not None else "-",
            "BM25": f"{h.get('bm25_score', 0.0):.2f}" if h.get("bm25_score") is not None else "-",
        })

    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
