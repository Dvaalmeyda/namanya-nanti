"""Komponen formulir unggah berkas multipart dan pemantau progres pengindeksan."""

import time
from typing import Optional
import streamlit as st
from frontend.client.document_client import DocumentClient
from frontend.client.system_client import SystemClient
from frontend.config import config


def render_file_uploader(available_folders: Optional[list[str]] = None) -> None:
    """Merender antarmuka unggah dokumen dan pemantauan pekerjaan indeks latar belakang."""
    st.subheader("Unggah Dokumen Baru")

    col_file, col_folder = st.columns([3, 2])
    with col_file:
        uploaded_file = st.file_uploader(
            "Pilih berkas dokumen",
            type=["pdf", "docx", "xlsx", "md", "txt"],
            help="Format yang didukung: PDF, DOCX, XLSX, Markdown, dan TXT.",
        )
    with col_folder:
        folder_input = st.text_input(
            "Subdirektori tujuan (opsional)",
            value="",
            placeholder="misal: keuangan / asuransi",
            help="Subfolder di dalam direktori dokumen.",
        )

    if st.button("Unggah dan Indeks Dokumen", disabled=(uploaded_file is None)):
        if uploaded_file is not None:
            doc_client = DocumentClient()
            system_client = SystemClient()

            with st.spinner("Mengunggah berkas ke backend..."):
                try:
                    res = doc_client.upload_document(
                        file_name=uploaded_file.name,
                        file_bytes=uploaded_file.getvalue(),
                        folder=folder_input.strip() or None,
                    )
                    st.success(f"Berkas `{uploaded_file.name}` berhasil diunggah.")
                    job_id = res.get("job_id")

                    # Pantau proses indexing dengan progress bar
                    _monitor_indexing_progress(system_client, job_id)
                except Exception as exc:
                    st.error(f"Gagal mengunggah dokumen: {exc}")


def _monitor_indexing_progress(system_client: SystemClient, job_id: Optional[str]) -> None:
    """Memantau progres pekerjaan indeksasi latar belakang."""
    progress_bar = st.progress(0, text="Menyiapkan pengindeksan...")
    status_text = st.empty()

    for _ in range(60):  # Maksimal 120 detik polling
        time.sleep(config.poll_interval_sec)
        try:
            status = system_client.get_index_status()
            is_running = status.get("status") == "running"
            pct = int(status.get("progress_percent", 0.0))
            current = status.get("current_file", "-")

            progress_bar.progress(min(pct, 100), text=f"Memproses: {current} ({pct}%)")

            if not is_running:
                if status.get("status") == "completed":
                    progress_bar.progress(100, text="Pengindeksan selesai.")
                    status_text.success("Indeks dokumen berhasil diperbarui.")
                elif status.get("status") == "failed":
                    status_text.error(f"Pengindeksan gagal: {status.get('errors')}")
                break
        except Exception:
            break
