"""Tampilan manajemen dokumen, pengunggahan, dan pemantau indeks (Documents View)."""

import pandas as pd
import streamlit as st
from frontend.client.document_client import DocumentClient
from frontend.client.system_client import SystemClient
from frontend.components.file_uploader import _monitor_indexing_progress, render_file_uploader
from frontend.utils.formatters import format_bytes, format_datetime


def render_documents_view() -> None:
    """Merender tab pengelolaan dokumen, pengunggahan berkas, dan sinkronisasi indeks."""
    tab_list, tab_upload, tab_sync = st.tabs(["Daftar Dokumen", "Unggah Dokumen Baru", "Sinkronisasi Indeks"])

    with tab_list:
        _render_document_list()

    with tab_upload:
        render_file_uploader()

    with tab_sync:
        _render_index_sync()


def _render_document_list() -> None:
    """Merender tabel daftar dokumen dan fitur penghapusan."""
    st.subheader("Dokumen yang Telah Terindeks")
    client = DocumentClient()

    try:
        docs = client.get_documents()
        if not docs:
            st.info("Belum ada dokumen yang terindeks.")
            return

        rows = []
        for d in docs:
            rows.append({
                "Nama Berkas": d.get("filename", "-"),
                "Jalur Relatif": d.get("rel_path", "-"),
                "Ukuran": format_bytes(d.get("file_size")),
                "Total Chunk": d.get("total_chunks", 0),
                "Perlu OCR": "Ya" if d.get("needs_ocr") else "Tidak",
                "Waktu Indeks": format_datetime(d.get("indexed_at")),
                "doc_id": d.get("doc_id"),
            })

        df = pd.DataFrame(rows)
        st.dataframe(df.drop(columns=["doc_id"]), use_container_width=True, hide_index=True)

        # Opsi hapus dokumen
        doc_options = {f"{r['Nama Berkas']} ({r['Jalur Relatif']})": r["doc_id"] for r in rows}
        selected_label = st.selectbox("Pilih dokumen untuk dihapus:", list(doc_options.keys()))

        if st.button("Hapus Dokumen Terpilih", type="secondary"):
            target_id = doc_options[selected_label]
            try:
                client.delete_document(target_id)
                st.success(f"Dokumen `{selected_label}` berhasil dihapus.")
                st.rerun()
            except Exception as exc:
                st.error(f"Gagal menghapus dokumen: {exc}")

    except Exception as exc:
        st.error(f"Gagal mengambil daftar dokumen: {exc}")


def _render_index_sync() -> None:
    """Merender status dan tombol pemicu sinkronisasi indeks."""
    st.subheader("Sinkronisasi Indeks Latar Belakang")
    sys_client = SystemClient()

    try:
        status = sys_client.get_index_status()
        is_running = status.get("status") == "running"

        st.caption(f"Status Terakhir: `{status.get('status', 'idle')}` | Waktu: `{status.get('completed_at') or status.get('started_at') or '-'}`")

        if st.button("Sinkronisasi Indeks Sekarang", disabled=is_running):
            try:
                res = sys_client.trigger_index_update()
                st.info(res.get("message", "Sinkronisasi dijadwalkan."))
                _monitor_indexing_progress(sys_client, res.get("job_id"))
                st.rerun()
            except Exception as exc:
                st.error(f"Gagal memicu sinkronisasi: {exc}")
    except Exception as exc:
        st.error(f"Gagal mengambil status indeks: {exc}")
