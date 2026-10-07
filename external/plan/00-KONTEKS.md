# KONTEKS PROYEK (wajib dibaca agent di awal setiap sesi fase)

## Tujuan
- Asisten AI tanya-jawab atas **dokumen pribadi milik satu pengguna** (polis, kontrak, catatan keuangan, SOP pribadi, materi belajar, dsb.).
- Berjalan **sepenuhnya lokal** dan **bisa dipakai tanpa internet** setelah model diunduh.
- Lingkup pengembangan **berhenti di API** yang bisa dicoba lewat Swagger (`/docs`). **Tidak ada frontend.**
- Prioritas: **keseimbangan kualitas jawaban dan kecepatan proses**. Setiap fitur yang menambah panggilan LLM wajib opsional (default mati) dan diukur dampaknya.

## Larangan
- Tidak ada panggilan ke layanan eksternal saat runtime: API LLM cloud, telemetry, tracing cloud, unduhan model diam-diam. Satu-satunya koneksi adalah Ollama di loopback.
- Tidak ada LangChain, LlamaIndex, atau vector database terpisah.
- Tidak menambah dependensi di luar daftar di bawah tanpa alasan tertulis di laporan.
- Tidak mengunduh model (`ollama pull`) tanpa konfirmasi pengguna.

## Lingkungan
- Laptop Windows 11, PowerShell. CPU i7-1165G7 (4 core / 8 thread), RAM 16 GB.
- GPU NVIDIA MX450 2 GB: Ollama **otomatis memakai GPU yang terdeteksi**. Jangan berasumsi CPU-only; ukur keduanya (lihat Fase 0).
- Kelak bisa pindah ke mesin lain/GPU: semua pengaturan lewat `.env` (pydantic-settings). Tidak ada path atau nama model yang di-hardcode.

## Stack
| Komponen | Pilihan |
|---|---|
| Bahasa dan paket | Python 3.11+, `uv`, `pyproject.toml` di **root workspace** (`e:\diva\ai engineer`), menggantikan `requirements.txt` |
| LLM | Ollama, baseline `qwen3:4b-instruct`, `think=False`. Model final dipilih di Fase 5 |
| Embedding | Ollama, baseline `bge-m3`. Model final dipilih di Fase 5. Prefix query/dokumen lewat config |
| Penyimpanan | **Satu file SQLite** (`data/index/index.db`, mode WAL): metadata, teks chunk, FTS5 (BM25), embedding (BLOB float32) |
| Dense search | Matriks numpy di memori (brute-force cosine), dimuat dari SQLite |
| API | FastAPI + Uvicorn (1 worker), Swagger di `/docs`, prefix `/api/v1` |
| Tes | pytest, pytest-socket (jaringan diblokir kecuali loopback), FastAPI TestClient |

Dependensi yang disetujui: `ollama`, `pydantic`, `pydantic-settings`, `pymupdf`, `python-docx`, `openpyxl`, `numpy`, `pyyaml`, `tqdm`, `fastapi`, `uvicorn`, `python-multipart`, `httpx`, `pytest`, `pytest-socket`.
Opsional (aktif lewat config, boleh dipasang bila fase memintanya): `pymupdf4llm`, `PySastrawi`, `pandas`.

## Data dan privasi
- Dokumen asli di `DOCS_DIR` (default `data/docs/`, gitignored). Dokumen dummy untuk pengembangan di `data/sample/`.
- Tes otomatis **hanya** memakai dokumen dummy. Dokumen asli tidak pernah dibaca oleh agent.
- Log berisi angka, ID, nama file, dan durasi. Isi dokumen dan isi pertanyaan **tidak** dicatat kecuali `LOG_CONTENT=true`.

## Konvensi kode
- Type hints di semua fungsi publik; Pydantic untuk skema dan validasi; dataclass untuk struktur internal.
- Fungsi kecil dan bernama jelas. Docstring singkat untuk fungsi publik.
- `async def` hanya bila seluruh I/O di dalamnya benar-benar async. Panggilan blocking (sqlite3, klien `ollama` sinkron, numpy berat) **tidak boleh** berada di `async def`; gunakan `def` (threadpool FastAPI) atau `ollama.AsyncClient`.
- Semua akses Ollama melalui satu modul `app/ollama_client.py`.

## Cara kerja agent
1. Baca file ini dan file fase yang diminta. Kerjakan **hanya** fase tersebut.
2. Tulis rencana singkat, lalu implementasi, tes, dan jalankan.
3. Jelaskan keputusan penting dalam 1-2 kalimat.
4. Berhenti dan laporkan: apa yang dibuat, hasil tes, angka yang diminta di "Kriteria selesai", dan kelemahan yang belum tertutup.
