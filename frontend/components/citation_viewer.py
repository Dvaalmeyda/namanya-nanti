"""Komponen penampil rujukan sitasi dan inspeksi teks potongan dokumen."""

from typing import Any
import streamlit as st
from frontend.client.document_client import DocumentClient
from frontend.utils.formatters import format_badge


def render_citations(sources: list[dict[str, Any]]) -> None:
    """Merender daftar kartu sumber rujukan dokumen yang dilampirkan pada jawaban."""
    if not sources:
        return

    st.markdown("**Sumber Rujukan Terverifikasi:**")
    doc_client = DocumentClient()

    for s in sources:
        n = s.get("n", 1)
        filename = s.get("filename", "-")
        location = s.get("location", "-")
        cited = s.get("cited", False)
        status_label = format_badge("DIRUJUK" if cited else "TIDAK DIRUJUK")

        dense = s.get("dense_score")
        dense_str = f"{dense:.3f}" if dense is not None else "-"
        bm25 = s.get("bm25_score")
        bm25_str = f"{bm25:.1f}" if bm25 is not None else "-"
        rrf = s.get("rrf_score", 0.0)

        header_text = f"[{n}] {filename} ({location}) - {status_label}"
        with st.expander(header_text):
            col_meta1, col_meta2 = st.columns(2)
            with col_meta1:
                st.caption(f"Path: `{s.get('rel_path', '-')}`")
                st.caption(f"Skor Dense: `{dense_str}` | Skor BM25: `{bm25_str}` | RRF: `{rrf:.5f}`")
            with col_meta2:
                also_in = s.get("also_in", [])
                if also_in:
                    st.caption(f"Dokumen Kembar (also_in): `{', '.join(also_in)}`")

            # Ambil atau tampilkan teks chunk
            chunk_text = s.get("text")
            chunk_id = s.get("chunk_id")
            if not chunk_text and chunk_id:
                try:
                    chunk_data = doc_client.get_chunk(chunk_id)
                    chunk_text = chunk_data.get("text")
                except Exception:
                    chunk_text = None

            if chunk_text:
                st.text_area("Isi Potongan Dokumen:", value=chunk_text, height=120, disabled=True, key=f"src_txt_{chunk_id}_{n}")
            else:
                st.info(f"Teks potongan `{chunk_id}` tidak termuat.")
