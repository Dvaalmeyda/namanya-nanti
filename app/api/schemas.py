"""Skema model request dan response Pydantic untuk REST API FastAPI.

Menyertakan contoh data lengkap (json_schema_extra) agar mempermudah pengujian via Swagger UI (/docs).
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    """Format respons kesalahan standar aplikasi."""

    code: str = Field(..., description="Kode error alfanumerik singkat")
    message: str = Field(..., description="Pesan penjelasan kesalahan yang dapat dipahami pengguna")
    detail: Optional[Any] = Field(None, description="Detail teknis atau petunjuk penyelesaian masalah")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "not_found",
                "message": "Dokumen dengan ID tersebut tidak ditemukan.",
                "detail": "doc_id: 'abc123xyz' tidak ada di tabel documents.",
            }
        }
    )


class HealthResponse(BaseModel):
    """Respons status kesehatan sistem, Ollama, dan indeks data."""

    status: str = Field(..., description="Status keseluruhan sistem ('ok' atau 'degraded')")
    ollama_connected: bool = Field(..., description="Status konektivitas ke server Ollama lokal")
    models_available: list[str] = Field(default_factory=list, description="Daftar model yang terpasang di Ollama")
    models_loaded: list[dict[str, Any]] = Field(default_factory=list, description="Model yang sedang termuat di memori")
    document_count: int = Field(..., description="Jumlah dokumen aktif di basis data")
    chunk_count: int = Field(..., description="Jumlah chunk aktif di basis data")
    index_version: str = Field(..., description="Versi indeks basis data saat ini")
    config_summary: dict[str, Any] = Field(default_factory=dict, description="Ringkasan konfigurasi model dan retrieval")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "ollama_connected": True,
                "models_available": ["qwen3:4b-instruct", "bge-m3:latest"],
                "models_loaded": [{"model": "qwen3:4b-instruct", "size_vram": 0}],
                "document_count": 6,
                "chunk_count": 19,
                "index_version": "1",
                "config_summary": {
                    "llm_model": "qwen3:4b-instruct",
                    "embed_model": "bge-m3",
                    "top_k": 4,
                    "num_ctx": 4096,
                },
            }
        }
    )


class ChatHistoryItem(BaseModel):
    """Satu giliran riwayat percakapan."""

    role: Literal["user", "assistant"] = Field(..., description="Peran pembicara")
    content: str = Field(..., description="Isi teks pesan")


class ChatFilters(BaseModel):
    """Filter metadata dokumen untuk membatasi ruang pencarian."""

    folders: Optional[list[str]] = Field(default=None, description="Daftar nama folder yang diizinkan")
    file_types: Optional[list[str]] = Field(default=None, description="Daftar ekstensi berkas yang diizinkan")
    doc_ids: Optional[list[str]] = Field(default=None, description="Daftar ID dokumen spesifik")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "folders": ["rumah", "keuangan"],
                "file_types": ["pdf", "docx"],
                "doc_ids": None,
            }
        }
    )


class ChatRequest(BaseModel):
    """Permintaan jawaban tanya-jawab RAG."""

    question: str = Field(..., min_length=1, max_length=2000, description="Teks pertanyaan pengguna")
    history: Optional[list[ChatHistoryItem]] = Field(default=None, description="Riwayat percakapan sebelumnya")
    filters: Optional[ChatFilters] = Field(default=None, description="Filter metadata dokumen opsional")
    top_k: Optional[int] = Field(default=None, ge=1, le=10, description="Jumlah potongan dokumen acuan")
    include_chunks: bool = Field(default=False, description="Sertakan teks mentah chunk dalam daftar sumber")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "Berapa total biaya sewa rumah dan bagaimana jadwal pembayarannya?",
                "history": [
                    {"role": "user", "content": "Apakah ada dokumen perjanjian sewa?"},
                    {"role": "assistant", "content": "Ya, terdapat Surat Perjanjian Sewa Menyewa Rumah Tinggal [1]."},
                ],
                "filters": {
                    "folders": ["rumah"],
                    "file_types": ["docx"],
                },
                "top_k": 4,
                "include_chunks": False,
            }
        }
    )


class SourceItem(BaseModel):
    """Metadata sumber rujukan dokumen yang disertakan pada jawaban."""

    n: int = Field(..., description="Nomor urut sitasi acuan [1], [2], dst.")
    doc_id: str = Field(..., description="ID unik dokumen")
    chunk_id: str = Field(..., description="ID unik potongan teks")
    filename: str = Field(..., description="Nama berkas dokumen")
    rel_path: str = Field(..., description="Jalur relatif dokumen")
    location: str = Field(..., description="Informasi lokasi (halaman, sheet, subjudul)")
    also_in: list[str] = Field(default_factory=list, description="Jalur berkas duplikat identik")
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rrf_score: float = Field(0.0, description="Skor fusi peringkat Reciprocal Rank Fusion")
    cited: bool = Field(False, description="Apakah nomor sitasi ini dirujuk secara eksplisit di jawaban")
    text: Optional[str] = Field(None, description="Teks mentah potongan (jika include_chunks=True)")


class ChatResponse(BaseModel):
    """Hasil jawaban lengkap RAG beserta daftar sitasi dan metrik latensi."""

    answer: str = Field(..., description="Teks jawaban dari asisten dokumen")
    sources: list[SourceItem] = Field(default_factory=list, description="Daftar potongan dokumen yang dijadikan acuan")
    refused: bool = Field(False, description="Apakah pertanyaan ditolak karena tidak relevan")
    refusal_reason: Optional[str] = Field(None, description="Alasan penolakan jika refused=True")
    timing: dict[str, Any] = Field(default_factory=dict, description="Rincian latensi proses dalam milidetik")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "Total biaya sewa rumah adalah Rp 75.000.000 untuk jangka waktu 2 tahun [1].",
                "sources": [
                    {
                        "n": 1,
                        "doc_id": "c1387d7f872ab684",
                        "chunk_id": "c1387d7f872ab684_0001",
                        "filename": "kontrak-sewa.docx",
                        "rel_path": "rumah/kontrak-sewa.docx",
                        "location": "Pasal 2: Biaya Sewa dan Jadwal Pembayaran",
                        "also_in": [],
                        "dense_score": 0.652,
                        "bm25_score": 14.82,
                        "rrf_score": 0.0328,
                        "cited": True,
                        "text": None,
                    }
                ],
                "refused": False,
                "refusal_reason": None,
                "timing": {
                    "embed_ms": 290.5,
                    "search_ms": 1.2,
                    "ttft_ms": 20450.0,
                    "total_ms": 25100.0,
                    "tokens_per_s": 6.2,
                },
            }
        }
    )


class SearchRequest(BaseModel):
    """Permintaan pencarian retrieval murni tanpa eksekusi LLM."""

    query: str = Field(..., min_length=1, max_length=2000, description="Kueri pencarian teks atau kata kunci")
    mode: Literal["hybrid", "dense", "bm25"] = Field("hybrid", description="Mode pencarian retrieval")
    top_k: Optional[int] = Field(default=None, ge=1, le=50, description="Batas jumlah hasil pencarian")
    filters: Optional[ChatFilters] = Field(default=None, description="Filter metadata dokumen")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "suku cadang filter oli SP-FLT-9902",
                "mode": "hybrid",
                "top_k": 5,
                "filters": {
                    "folders": ["kendaraan"],
                    "file_types": ["md"],
                },
            }
        }
    )


class SearchHitItem(BaseModel):
    """Satu potongan dokumen yang cocok pada pencarian."""

    rank: int = Field(..., description="Peringkat urutan hasil pencarian (1-indexed)")
    chunk_id: str = Field(..., description="ID unik chunk")
    doc_id: str = Field(..., description="ID dokumen induk")
    rel_path: str = Field(..., description="Jalur relatif berkas")
    filename: str = Field(..., description="Nama berkas")
    location: str = Field(..., description="Lokasi di dalam berkas")
    snippet: str = Field(..., description="Cuplikan awal teks (maksimal 200 karakter)")
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rrf_score: float = Field(0.0, description="Skor gabungan Reciprocal Rank Fusion")
    also_in: list[str] = Field(default_factory=list, description="Jalur berkas duplikat identik")


class SearchResponse(BaseModel):
    """Hasil pencarian retrieval murni."""

    query: str = Field(..., description="Kueri pencarian yang diproses")
    mode: str = Field(..., description="Mode retrieval yang digunakan")
    hits: list[SearchHitItem] = Field(default_factory=list, description="Daftar potongan dokumen yang ditemukan")
    total_hits: int = Field(..., description="Jumlah total potongan dokumen yang cocok")
    refused: bool = Field(False, description="Apakah kueri ditolak oleh gerbang relevansi")
    refusal_reason: Optional[str] = Field(None, description="Alasan penolakan")
    timing: dict[str, Any] = Field(default_factory=dict, description="Metrik durasi pencarian")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "SP-FLT-9902",
                "mode": "hybrid",
                "hits": [
                    {
                        "rank": 1,
                        "chunk_id": "e4589d31872ab111_0002",
                        "doc_id": "e4589d31872ab111",
                        "rel_path": "kendaraan/catatan-servis.md",
                        "filename": "catatan-servis.md",
                        "location": "Catatan Riwayat Servis Kendaraan",
                        "snippet": "Servis Berkala 20.000 km: Penggantian Filter Oli (Part No: SP-FLT-9902) dan Oli Mesin Full Synthetic...",
                        "dense_score": 0.28,
                        "bm25_score": 24.15,
                        "rrf_score": 0.0164,
                        "also_in": [],
                    }
                ],
                "total_hits": 1,
                "refused": False,
                "refusal_reason": None,
                "timing": {"embed_ms": 280.0, "search_ms": 1.1, "total_ms": 281.5},
            }
        }
    )


class DocumentItem(BaseModel):
    """Metadata ringkas satu dokumen terindeks."""

    doc_id: str = Field(..., description="ID unik dokumen (16 karakter hex sha1)")
    rel_path: str = Field(..., description="Jalur relatif dokumen dari direktori dokumen")
    filename: str = Field(..., description="Nama berkas dokumen")
    file_type: str = Field(..., description="Ekstensi berkas dokumen (pdf, docx, xlsx, md, txt)")
    folder: str = Field(..., description="Folder induk relatif")
    size: int = Field(..., description="Ukuran berkas dalam byte")
    mtime: float = Field(..., description="Waktu modifikasi berkas terakhir (timestamp)")
    n_chunks: int = Field(..., description="Jumlah potongan teks terindeks")
    needs_ocr: bool = Field(..., description="Apakah dokumen terdeteksi memerlukan OCR")
    indexed_at: str = Field(..., description="Waktu dokumen diindeks (format ISO)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "doc_id": "c1387d7f872ab684",
                "rel_path": "rumah/kontrak-sewa.docx",
                "filename": "kontrak-sewa.docx",
                "file_type": "docx",
                "folder": "rumah",
                "size": 24576,
                "mtime": 1740000000.0,
                "n_chunks": 3,
                "needs_ocr": False,
                "indexed_at": "2025-01-10T10:00:00",
            }
        }
    )


class DocumentListResponse(BaseModel):
    """Daftar dokumen terindeks dengan informasi paginasi."""

    documents: list[DocumentItem] = Field(default_factory=list, description="Kumpulan metadata dokumen")
    total: int = Field(..., description="Total dokumen yang cocok dengan filter")
    limit: int = Field(..., description="Batas jumlah dokumen per halaman")
    offset: int = Field(..., description="Offset pergeseran dokumen")


class ChunkMetaItem(BaseModel):
    """Metadata potongan teks (tanpa teks mentah) untuk detail dokumen."""

    chunk_id: str = Field(..., description="ID unik chunk")
    idx: int = Field(..., description="Indeks urutan chunk dalam dokumen")
    page: Optional[int] = Field(None, description="Nomor halaman awal")
    page_end: Optional[int] = Field(None, description="Nomor halaman akhir")
    sheet: Optional[str] = Field(None, description="Nama lembar kerja Excel")
    section: Optional[str] = Field(None, description="Nama heading atau bab")
    kind: str = Field(..., description="Jenis potongan ('text' atau 'table')")
    location: str = Field(..., description="Format representasi lokasi")
    has_embedding: bool = Field(..., description="Status keberadaan vektor embedding")


class DocumentDetailResponse(BaseModel):
    """Detail lengkap dokumen beserta metadata potongan chunk."""

    document: DocumentItem = Field(..., description="Metadata dokumen utama")
    chunks: list[ChunkMetaItem] = Field(default_factory=list, description="Daftar metadata potongan teks dokumen")


class ChunkDetailResponse(BaseModel):
    """Teks lengkap dan metadata potongan dokumen yang disitasi."""

    chunk_id: str = Field(..., description="ID unik potongan teks")
    doc_id: str = Field(..., description="ID dokumen induk")
    filename: str = Field(..., description="Nama berkas dokumen")
    rel_path: str = Field(..., description="Jalur relatif berkas dokumen")
    idx: int = Field(..., description="Urutan potongan dalam dokumen")
    location: str = Field(..., description="Lokasi potongan")
    kind: str = Field(..., description="Jenis potongan ('text' atau 'table')")
    text: str = Field(..., description="Teks isi lengkap potongan dokumen")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chunk_id": "c1387d7f872ab684_0001",
                "doc_id": "c1387d7f872ab684",
                "filename": "kontrak-sewa.docx",
                "rel_path": "rumah/kontrak-sewa.docx",
                "idx": 1,
                "location": "Pasal 2: Biaya Sewa dan Jadwal Pembayaran",
                "kind": "text",
                "text": "Pasal 2: Biaya Sewa dan Jadwal Pembayaran\nTotal biaya sewa rumah tinggal ini adalah Rp 75.000.000...",
            }
        }
    )


class JobAcceptedResponse(BaseModel):
    """Respons penerimaan pekerjaan latar belakang."""

    job_id: str = Field(..., description="ID unik pekerjaan yang dijadwalkan")
    status: str = Field("running", description="Status pekerjaan awal")
    message: str = Field(..., description="Pesan konfirmasi")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "job_20261008_131500_1234",
                "status": "running",
                "message": "Pekerjaan sinkronisasi pengindeksan dokumen telah dijadwalkan di latar belakang.",
            }
        }
    )


class IndexStatusResponse(BaseModel):
    """Status pekerjaan sinkronisasi pengindeksan dokumen."""

    status: Literal["idle", "running", "completed", "failed"] = Field(..., description="Status eksekusi saat ini")
    job_id: Optional[str] = Field(None, description="ID pekerjaan pengindeksan terakhir")
    progress_percent: float = Field(0.0, description="Persentase kemajuan pemrosesan (0 - 100)")
    current_file: Optional[str] = Field(None, description="Nama berkas yang sedang diproses saat ini")
    current_index: int = Field(0, description="Urutan berkas yang sedang diproses")
    total_files: int = Field(0, description="Total berkas yang akan diproses")
    eta_seconds: Optional[float] = Field(None, description="Estimasi sisa waktu proses dalam detik")
    report: Optional[dict[str, Any]] = Field(None, description="Ringkasan hasil sinkronisasi jika sudah selesai")
    started_at: Optional[str] = Field(None, description="Waktu mulai pekerjaan (format ISO)")
    completed_at: Optional[str] = Field(None, description="Waktu selesai pekerjaan (format ISO)")
    errors: list[str] = Field(default_factory=list, description="Daftar pesan kesalahan selama proses pengindeksan")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "completed",
                "job_id": "job_20261008_131500_1234",
                "progress_percent": 100.0,
                "current_file": None,
                "current_index": 6,
                "total_files": 6,
                "eta_seconds": 0.0,
                "report": {
                    "added": 1,
                    "updated": 0,
                    "deleted": 0,
                    "skipped": 5,
                    "failed": 0,
                    "total_chunks": 3,
                    "duration_s": 2.45,
                },
                "started_at": "2026-10-08T13:15:00",
                "completed_at": "2026-10-08T13:15:02",
                "errors": [],
            }
        }
    )


class SystemLogsResponse(BaseModel):
    """Hasil pembacaan log sistem backend."""

    log_file: str = Field(..., description="Nama atau jalur berkas log")
    total_lines: int = Field(..., description="Jumlah baris log yang dikembalikan")
    logs: list[str] = Field(default_factory=list, description="Daftar baris teks log")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "log_file": "data/index/app.log",
                "total_lines": 2,
                "logs": [
                    "2026-10-09 14:00:00 | INFO    | app.api.main | Server started",
                    "2026-10-09 14:00:01 | INFO    | app.indexing | Indexing completed",
                ],
            }
        }
    )

