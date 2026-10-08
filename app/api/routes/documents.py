"""Endpoint pengelolaan dokumen, unggah multipart, penghapusan, dan pembacaan chunk."""

import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.api.deps import get_app_settings, get_db_conn, get_job_manager, get_vector_index, verify_api_key
from app.api.jobs import IndexingJobManager, JobConflictError
from app.api.schemas import (
    ChunkDetailResponse,
    ChunkMetaItem,
    DocumentDetailResponse,
    DocumentItem,
    DocumentListResponse,
    JobAcceptedResponse,
)
from app.config import Settings
from app import store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"], dependencies=[Depends(verify_api_key)])

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".md", ".txt"}


def _sanitize_folder(folder_str: str) -> str:
    """Memvalidasi dan membersihkan string folder untuk mencegah path traversal."""
    f = folder_str.strip()
    if not f:
        return ""

    # Tolak path traversal, drive letter, atau root absolut
    if ".." in f or re.search(r"^[a-zA-Z]:", f) or f.startswith("/") or f.startswith("\\"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_folder",
                "message": "Parameter folder tidak valid atau berpotensi path traversal.",
                "detail": f"Folder '{folder_str}' dilarang karena mengandung karakter berbahaya.",
            },
        )

    # Normalisasi path
    norm_parts = [p for p in Path(f).parts if p not in (".", "/", "\\")]
    return "/".join(norm_parts)


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="Daftar dokumen terindeks",
    description="Mengambil daftar metadata dokumen yang tersimpan di basis data dengan filter folder, tipe berkas, dan paginasi.",
)
def list_documents(
    folder: Optional[str] = Query(None, description="Filter nama folder"),
    file_type: Optional[str] = Query(None, description="Filter tipe berkas (pdf, docx, xlsx, md, txt)"),
    limit: int = Query(50, ge=1, le=500, description="Jumlah dokumen per halaman"),
    offset: int = Query(0, ge=0, description="Offset pergeseran dokumen"),
    conn: sqlite3.Connection = Depends(get_db_conn),
) -> DocumentListResponse:
    """Mengambil daftar dokumen terindeks secara berhalaman."""
    where_clauses: list[str] = []
    params: list[object] = []

    if folder:
        where_clauses.append("folder = ?")
        params.append(folder)

    if file_type:
        where_clauses.append("file_type = ?")
        params.append(file_type.lower().lstrip("."))

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Hitung total
    cur_count = conn.execute(f"SELECT count(*) AS total FROM documents {where_sql};", params)
    total = cur_count.fetchone()["total"]

    # Ambil baris
    query_sql = f"""
        SELECT * FROM documents
        {where_sql}
        ORDER BY rel_path ASC
        LIMIT ? OFFSET ?;
    """
    cur_docs = conn.execute(query_sql, params + [limit, offset])
    rows = cur_docs.fetchall()

    docs: list[DocumentItem] = []
    for r in rows:
        docs.append(
            DocumentItem(
                doc_id=r["doc_id"],
                rel_path=r["rel_path"],
                filename=r["filename"],
                file_type=r["file_type"],
                folder=r["folder"],
                size=r["size"],
                mtime=r["mtime"],
                n_chunks=r["n_chunks"],
                needs_ocr=bool(r["needs_ocr"]),
                indexed_at=r["indexed_at"],
            )
        )

    return DocumentListResponse(
        documents=docs,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/documents/{doc_id}",
    response_model=DocumentDetailResponse,
    summary="Detail dokumen dan daftar chunk",
    description="Mengambil detail metadata dokumen beserta daftar potongan teks chunk (tanpa teks mentah).",
)
def get_document_detail(
    doc_id: str,
    conn: sqlite3.Connection = Depends(get_db_conn),
) -> DocumentDetailResponse:
    """Mengambil detail dokumen spesifik dan metadata potongan chunk."""
    doc_rec = store.get_document(conn, doc_id)
    if not doc_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Dokumen dengan ID '{doc_id}' tidak ditemukan.",
            },
        )

    doc_item = DocumentItem(
        doc_id=doc_rec["doc_id"],
        rel_path=doc_rec["rel_path"],
        filename=doc_rec["filename"],
        file_type=doc_rec["file_type"],
        folder=doc_rec["folder"],
        size=doc_rec["size"],
        mtime=doc_rec["mtime"],
        n_chunks=doc_rec["n_chunks"],
        needs_ocr=bool(doc_rec["needs_ocr"]),
        indexed_at=doc_rec["indexed_at"],
    )

    chunks_data = store.get_chunks_by_doc_id(conn, doc_id)
    chunk_items: list[ChunkMetaItem] = []
    for ch in chunks_data:
        chunk_items.append(
            ChunkMetaItem(
                chunk_id=ch["chunk_id"],
                idx=ch["idx"],
                page=ch["page"],
                page_end=ch["page_end"],
                sheet=ch["sheet"],
                section=ch["section"],
                kind=ch["kind"],
                location=ch["location"],
                has_embedding=bool(ch["embedding"] and len(ch["embedding"]) > 0),
            )
        )

    return DocumentDetailResponse(document=doc_item, chunks=chunk_items)


@router.post(
    "/documents",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Unggah berkas dokumen baru",
    description="Mengunggah berkas multipart (PDF, DOCX, XLSX, MD, TXT), memvalidasi ukuran dan nama berkas, menyimpan ke direktori dokumen, dan menjadwalkan pekerjaan sinkronisasi indeks di latar belakang.",
)
def upload_document(
    file: UploadFile = File(..., description="Berkas yang diunggah"),
    folder: str = Form("", description="Nama subfolder relatif di dalam direktori dokumen"),
    settings: Settings = Depends(get_app_settings),
    manager: IndexingJobManager = Depends(get_job_manager),
    vindex: store.VectorIndex = Depends(get_vector_index),
) -> JobAcceptedResponse:
    """Memproses unggah berkas multipart dan menjadwalkan pengindeksan."""
    raw_filename = file.filename or ""
    safe_filename = Path(raw_filename).name.strip()

    if not safe_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "bad_request", "message": "Nama berkas tidak boleh kosong."},
        )

    # Validasi ekstensi
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "unsupported_media_type",
                "message": f"Tipe berkas '{suffix}' tidak didukung.",
                "detail": f"Format yang didukung adalah: {sorted(list(SUPPORTED_EXTENSIONS))}",
            },
        )

    # Validasi folder
    clean_folder = _sanitize_folder(folder)

    # Siapkan direktori tujuan
    target_dir = settings.DOCS_DIR / clean_folder if clean_folder else settings.DOCS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    destination_file = target_dir / safe_filename

    # Tulis ke file sementara untuk verifikasi ukuran (MAX_UPLOAD_MB)
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    temp_dir = settings.DOCS_DIR / ".temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        total_bytes = 0
        chunk_size = 1024 * 1024  # 1 MB

        try:
            while True:
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    tmp.close()
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail={
                            "code": "payload_too_large",
                            "message": f"Ukuran berkas melebihi batas maksimum {settings.MAX_UPLOAD_MB} MB.",
                            "detail": f"Ukuran terdeteksi melebihi {max_bytes} byte.",
                        },
                    )
                tmp.write(chunk)
        except HTTPException:
            raise
        except Exception as exc:
            tmp.close()
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "upload_error", "message": f"Gagal menyimpan berkas sementara: {exc}"},
            )

    # Pindahkan berkas sementara ke tujuan akhir secara atomik
    try:
        shutil.move(str(tmp_path), str(destination_file))
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "move_error", "message": f"Gagal memindahkan berkas ke direktori tujuan: {exc}"},
        )

    # Jadwalkan pekerjaan sinkronisasi indeks di latar belakang
    try:
        job_id = manager.start_job(root_dir=settings.DOCS_DIR, settings=settings, vector_index=vindex)
    except JobConflictError as conflict_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "job_conflict",
                "message": "Berkas tersimpan, tetapi pekerjaan pengindeksan lain sedang berjalan.",
                "detail": str(conflict_err),
            },
        )

    return JobAcceptedResponse(
        job_id=job_id,
        status="running",
        message=f"Berkas '{safe_filename}' berhasil diunggah. Pekerjaan pengindeksan telah dijadwalkan.",
    )


@router.delete(
    "/documents/{doc_id}",
    summary="Hapus dokumen dari indeks",
    description="Menghapus dokumen dari indeks basis data SQLite. Jika delete_file=true, berkas fisik di disk juga akan dihapus.",
)
def delete_document(
    doc_id: str,
    delete_file: bool = Query(False, description="Hapus juga berkas fisik dari disk jika true"),
    settings: Settings = Depends(get_app_settings),
    conn: sqlite3.Connection = Depends(get_db_conn),
    vindex: store.VectorIndex = Depends(get_vector_index),
) -> dict[str, Any]:
    """Menghapus dokumen dari indeks dan disk jika diminta."""
    doc_rec = store.get_document(conn, doc_id)
    if not doc_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Dokumen dengan ID '{doc_id}' tidak ditemukan di basis data.",
            },
        )

    rel_path = doc_rec["rel_path"]

    # Hapus dari indeks SQLite
    store.delete_document(conn, doc_id)

    # Segarkan vector index di memori
    vindex.refresh_if_stale(conn)

    disk_deleted = False
    if delete_file:
        file_path = settings.DOCS_DIR / rel_path
        if file_path.exists():
            try:
                file_path.unlink()
                disk_deleted = True
            except Exception as exc:
                logger.warning("Gagal menghapus berkas fisik %s: %s", file_path, exc)

    return {
        "status": "success",
        "doc_id": doc_id,
        "message": f"Dokumen '{doc_rec['filename']}' berhasil dihapus dari indeks.",
        "file_deleted": disk_deleted,
    }


@router.get(
    "/chunks/{chunk_id}",
    response_model=ChunkDetailResponse,
    summary="Ambil teks lengkap potongan dokumen",
    description="Mengambil teks isi lengkap dan informasi lokasi dari potongan dokumen tertentu berdasarkan chunk_id yang disitasi.",
)
def get_chunk_detail(
    chunk_id: str,
    conn: sqlite3.Connection = Depends(get_db_conn),
) -> ChunkDetailResponse:
    """Mengambil rincian teks lengkap potongan chunk."""
    sql = """
        SELECT c.*, d.filename, d.rel_path
        FROM chunks c
        JOIN documents d ON c.doc_id = d.doc_id
        WHERE c.chunk_id = ?;
    """
    cur = conn.execute(sql, (chunk_id,))
    row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Potongan teks dengan chunk_id '{chunk_id}' tidak ditemukan.",
            },
        )

    return ChunkDetailResponse(
        chunk_id=row["chunk_id"],
        doc_id=row["doc_id"],
        filename=row["filename"],
        rel_path=row["rel_path"],
        idx=row["idx"],
        location=row["location"],
        kind=row["kind"],
        text=row["text"],
    )
