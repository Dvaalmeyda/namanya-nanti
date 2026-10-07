# FASE 4 - API (FastAPI + Swagger)

> Prasyarat: Fase 3 selesai.
> Baca `00-KONTEKS.md` terlebih dahulu.

## TUGAS
Bangun API di atas `retrieval` dan `rag` dari Fase 3. Antarmuka uji utama adalah Swagger UI (`/docs`), jadi setiap endpoint harus nyaman dicoba dari sana: skema Pydantic lengkap, deskripsi, dan contoh request yang sudah terisi.

Field config baru: `API_HOST=127.0.0.1`, `API_PORT=8000`, `API_KEY=""` (kosong = autentikasi mati), `WARMUP=true`, `MAX_CONCURRENT_CHAT=1`, `MAX_UPLOAD_MB=50`, `UPLOAD_SUBDIR=uploads`.

### 1. Struktur
- `app/api/main.py`: app factory `create_app()`, lifespan, registrasi router dengan prefix `/api/v1`, exception handler.
- `app/api/schemas.py`: semua model request/response (dengan `json_schema_extra` berisi contoh).
- `app/api/deps.py`: dependency injection untuk settings, store, vector index, autentikasi, semaphore chat.
- `app/api/jobs.py`: manajer job indexing di background (satu job aktif pada satu waktu).
- `app/api/routes/`: `health.py`, `chat.py`, `search.py`, `documents.py`, `index.py`.
- Jalankan: `uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 1`.

### 2. Lifespan (startup/shutdown)
- `apply_offline_env()`, `assert_local_only(OLLAMA_HOST)`; startup gagal dengan pesan jelas bila host non-loopback tanpa `ALLOW_REMOTE=true`.
- Buka `Store`, muat `VectorIndex`.
- Bila `WARMUP=true`: panggil `ollama_client.warmup()` agar pertanyaan pertama tidak menunggu model dimuat. Bila Ollama belum hidup, API tetap start dan `/health` melaporkan statusnya.
- Shutdown: tutup koneksi, tunggu job indexing berhenti dengan aman.

### 3. Endpoint (`/api/v1`)
| Method | Path | Fungsi | Catatan |
|---|---|---|---|
| GET | `/health` | Status Ollama, model tersedia/termuat (dan porsi GPU), jumlah dokumen/chunk, `index_version`, ringkasan config (model, TOP_K) | Tanpa autentikasi |
| POST | `/chat` | Jawaban **JSON utuh** (`RagResult`) | Endpoint utama untuk Swagger |
| POST | `/chat/stream` | SSE: `token`, `sources`, `done`, `error` | Untuk klien selain Swagger (curl, frontend kelak) |
| POST | `/search` | Retrieval saja tanpa LLM: hit dengan skor dense/BM25/RRF dan cuplikan 200 karakter | Untuk memisahkan masalah retrieval dari masalah jawaban |
| GET | `/documents` | Daftar dokumen terindeks, filter `folder`/`file_type`, paginasi `limit`/`offset` | |
| GET | `/documents/{doc_id}` | Detail dokumen + daftar chunk (tanpa teks) | |
| POST | `/documents` | Upload file (multipart) ke `DOCS_DIR/<folder>/`, lalu jadwalkan job `sync` incremental (file lain dilewati dengan cepat) | 202 + `job_id` |
| DELETE | `/documents/{doc_id}` | Hapus dari index; `delete_file=true` juga menghapus file di disk | |
| GET | `/chunks/{chunk_id}` | Isi lengkap chunk yang disitasi | |
| POST | `/index/update` | Jalankan `sync` incremental di background | 202 + `job_id`; 409 bila job lain berjalan |
| GET | `/index/status` | Status job terakhir: progres, ETA, ringkasan `SyncReport`, error per file | |

### 4. Skema utama
- `ChatRequest`: `question` (1-2000 karakter), `history` (opsional, maks `HISTORY_TURNS` giliran), `filters` (`folders`, `file_types`, `doc_ids`), `top_k` (opsional, 1-10), `include_chunks` (bool, default false: sertakan teks chunk di `sources` untuk debug).
- `ChatResponse`: dari `RagResult` (answer, sources, refused, refusal_reason, timing).
- `SearchRequest`: `query`, `mode` (`hybrid` | `dense` | `bm25`), `top_k`, `filters`.
- `ErrorResponse` konsisten: `code`, `message`, `detail`.

### 5. Perilaku penting
- **Tidak ada panggilan blocking di `async def`.** Endpoint yang memanggil sqlite3, numpy, atau klien `ollama` sinkron ditulis sebagai `def` (dijalankan di threadpool). SSE memakai generator sinkron di `StreamingResponse` atau `ollama.AsyncClient`, pilih salah satu dan jelaskan alasannya.
- **Antrean chat**: semaphore `MAX_CONCURRENT_CHAT` (default 1). Di CPU, Ollama efektif memproses satu generasi per waktu; antrean lebih baik daripada saling memperlambat. Permintaan yang menunggu terlalu lama mendapat 503 dengan pesan jelas.
- **Refresh index**: setelah job indexing selesai, `VectorIndex.refresh_if_stale()` dipanggil di bawah lock lalu diganti secara atomik; permintaan yang sedang berjalan tetap memakai matriks lama.
- **Kode status**: 404 (dokumen/chunk tidak ada), 409 (job indexing bentrok), 413 (file terlalu besar), 415 (tipe file tidak didukung), 422 (validasi), 503 (Ollama tidak tersedia atau model belum di-pull, dengan perintah perbaikan di `detail`).
- **Autentikasi opsional**: bila `API_KEY` diisi, semua endpoint kecuali `/health` membutuhkan header `X-API-Key` (`APIKeyHeader`, sehingga tombol "Authorize" muncul di Swagger). Bandingkan dengan `secrets.compare_digest`.

### 6. Hardening ringan
- Bind ke `127.0.0.1` secara default; CORS tidak diaktifkan.
- Upload: validasi ekstensi dan ukuran, nama file disanitasi, parameter `folder` tidak boleh keluar dari `DOCS_DIR` (tolak `..`, path absolut, drive letter). File ditulis ke file sementara lalu dipindah.
- Tidak ada endpoint yang mengembalikan prompt sistem atau prompt lengkap.
- Log request: method, path, status, durasi, ukuran hasil. Tanpa isi pertanyaan atau jawaban (kecuali `LOG_CONTENT=true`).

## BATASAN
- Tidak ada frontend atau file statis.
- Jangan menyimpan percakapan di server.
- Jangan membuka port ke luar localhost.

## KRITERIA SELESAI
- Tes `TestClient` (LLM dan embedding palsu, index sample sementara di `tmp_path`):
  - `/chat` mengembalikan skema lengkap; penolakan menghasilkan `refused=true` tanpa memanggil LLM.
  - `/chat/stream` mengirim event dengan urutan `token` lalu `sources` lalu `done`.
  - `/search` untuk ketiga mode.
  - Upload lalu job selesai lalu dokumen muncul di `/documents` dan bisa ditemukan di `/search`; `DELETE` menghilangkannya dari hasil.
  - Path traversal di upload ditolak; tipe file tidak didukung ditolak (415); file terlalu besar ditolak (413).
  - `/index/update` kedua saat job berjalan mendapat 409.
  - `API_KEY` terisi: tanpa header 401, dengan header benar 200, `/health` tetap terbuka.
  - Ollama mati: `/chat` 503 dengan pesan jelas, `/health` melaporkan status.
  - `OLLAMA_HOST` non-loopback tanpa `ALLOW_REMOTE`: startup gagal.
- Cek manual: jalankan server, buka `http://127.0.0.1:8000/docs`, lakukan upload, update index, search, dan chat dari Swagger. Tuliskan langkahnya di README beserta contoh `curl` untuk `/chat/stream`.
- Laporkan latensi `/chat` end-to-end untuk 3 pertanyaan sample (pertama setelah startup dan berikutnya) untuk memastikan warm-up efektif.
