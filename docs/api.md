# Spesifikasi REST API

Dokumentasi teknis antarmuka REST API untuk Personal Document Assistant. Seluruh endpoint menggunakan prefiks jalur `/api/v1` dan berjalan secara lokal di `http://127.0.0.1:8000`.

---

## 1. Antarmuka Dokumentasi Interaktif

Setelah server API berjalan, dokumentasi interaktif berbasis skema OpenAPI dapat diakses langsung melalui peramban web:

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 2. Autentikasi

Autentikasi bersifat opsional dan dikendalikan oleh variabel lingkungan `API_KEY`:

- Jika `API_KEY` tidak diatur (kosong), seluruh endpoint dapat diakses tanpa kredensial.
- Jika `API_KEY` diatur di berkas `.env`, klien wajib menyertakan header HTTP:
  ```http
  X-API-Key: kunci-rahasia-anda
  ```
- Permintaan tanpa header atau dengan kunci yang tidak cocok akan menerima tanggapan `401 Unauthorized`.

---

## 3. Daftar Endpoint

### 3.1 Status Sistem (`GET /api/v1/health`)
Memeriksa status operasional server, konektivitas Ollama, daftar model yang terpasang dan termuat di RAM, serta ringkasan indeks dokumen.

- **Format Tanggapan (`200 OK`)**:
  ```json
  {
    "status": "healthy",
    "version": "0.1.0",
    "ollama": {
      "connected": true,
      "installed_models": ["qwen3:4b-instruct", "bge-m3:latest"],
      "running_models": ["qwen3:4b-instruct"]
    },
    "index": {
      "total_documents": 6,
      "total_chunks": 42,
      "index_version": "v1.0"
    }
  }
  ```

#### Pembacaan Log Sistem Backend (`GET /api/v1/system/logs`)
Membaca baris-baris log terproteksi dari berkas `data/index/app.log` yang telah disanitasi oleh `RedactionFilter`.

- **Parameter Query**:
  - `lines` (`int`, default: 100): Jumlah baris terakhir yang diambil.
  - `level` (`string`, opsional): Filter level log (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
  - `search` (`string`, opsional): Pencarian kata kunci teks dalam log.
- **Format Tanggapan (`200 OK`)**:
  ```json
  {
    "log_file": "data/index/app.log",
    "total_lines": 2,
    "logs": [
      "2026-10-09 14:00:00 | INFO    | app.api.main | Server started",
      "2026-10-09 14:00:01 | INFO    | app.indexing | Indexing completed"
    ]
  }
  ```

---

### 3.2 Tanya-Jawab Dokumen Non-Streaming (`POST /api/v1/chat`)
Menjalankan alur RAG lengkap untuk menjawab pertanyaan berdasarkan dokumen terindeks dalam bentuk respons JSON utuh.

- **Format Permintaan**:
  ```json
  {
    "question": "Berapa biaya sewa rumah dan berapa lama masa sewanya?",
    "history": [
      {"role": "user", "content": "Siapa pemilik rumah yang disewakan?"},
      {"role": "assistant", "content": "Pemilik rumah adalah Bambang Sutrisno [1]."}
    ],
    "filters": {
      "folders": ["rumah"]
    },
    "top_k": 4
  }
  ```
- **Format Tanggapan (`200 OK`)**:
  ```json
  {
    "answer": "Total biaya sewa rumah tinggal adalah Rp 75.000.000 untuk jangka waktu 2 tahun [1].",
    "refused": false,
    "refusal_reason": null,
    "sources": [
      {
        "n": 1,
        "doc_id": "rumah_kontrak_sewa_docx",
        "chunk_id": "rumah_kontrak_sewa_docx_c0001",
        "filename": "kontrak-sewa.docx",
        "rel_path": "rumah/kontrak-sewa.docx",
        "location": "Pasal 2: Biaya Sewa dan Jadwal Pembayaran",
        "also_in": [],
        "dense_score": 0.7241,
        "bm25_score": 9.152,
        "rrf_score": 0.0328,
        "cited": true
      }
    ],
    "timing": {
      "embed_ms": 320.5,
      "search_ms": 1.1,
      "ttft_ms": 0.0,
      "tokens_per_s": 6.2,
      "total_ms": 6850.2
    }
  }
  ```

---

### 3.3 Tanya-Jawab Dokumen Streaming (`POST /api/v1/chat/stream`)
Menjalankan alur RAG dengan mengalirkan token jawaban secara bertahap menggunakan protokol Server-Sent Events (SSE).

- **Header Tanggapan**: `Content-Type: text/event-stream`
- **Format Aliran Peristiwa (SSE Events)**:
  - Potongan token teks:
    ```
    data: {"type": "chunk", "text": "Total "}
    data: {"type": "chunk", "text": "biaya "}
    data: {"type": "chunk", "text": "sewa..."}
    ```
  - Pesan selesai (*done*) yang memuat daftar sumber dan profil waktu:
    ```
    data: {"type": "done", "sources": [...], "refused": false, "timing": {...}}
    ```

---

### 3.4 Pencarian Potongan Dokumen Saja (`POST /api/v1/search`)
Melakukan retrieval potongan dokumen tanpa memanggil model bahasa (LLM). Berguna untuk pengujian retrieval dan integrasi pencarian mandiri.

- **Format Permintaan**:
  ```json
  {
    "query": "kampas rem depan HR-V",
    "mode": "hybrid",
    "top_k": 3,
    "filters": {
      "folders": ["kendaraan"]
    }
  }
  ```
- **Pilihan Mode**: `hybrid`, `dense`, `bm25`.
- **Format Tanggapan (`200 OK`)**:
  ```json
  {
    "query": "kampas rem depan HR-V",
    "mode": "hybrid",
    "total_hits": 2,
    "hits": [
      {
        "chunk_id": "kendaraan_catatan_servis_md_c0002",
        "doc_id": "kendaraan_catatan_servis_md",
        "filename": "catatan-servis.md",
        "rel_path": "kendaraan/catatan-servis.md",
        "location": "Servis 30.000 KM - Tanggal 10 Februari 2025",
        "text_preview": "Kampas rem depan: Kode SP-BRK-4021 (Rp 850.000)...",
        "score": 0.0328,
        "dense_score": 0.651,
        "bm25_score": 8.42
      }
    ],
    "timing": {
      "embed_ms": 310.2,
      "search_ms": 1.0,
      "total_ms": 311.2
    }
  }
  ```

---

### 3.5 Manajemen Dokumen

#### Daftar Dokumen (`GET /api/v1/documents`)
Mengambil daftar dokumen yang tersimpan dalam indeks. Mendukung filter folder: `GET /api/v1/documents?folder=rumah`.

#### Detail Dokumen (`GET /api/v1/documents/{doc_id}`)
Mengambil informasi terperinci satu dokumen beserta daftar ID potongan teks yang dimilikinya.

#### Unggah Dokumen Baru (`POST /api/v1/documents`)
Mengunggah berkas dokumen menggunakan `multipart/form-data`:
- **Parameter Form**:
  - `file`: Berkas biner (`.pdf`, `.docx`, `.xlsx`, `.md`, atau `.txt`).
  - `folder` (opsional): Subdirektori penyimpanan di dalam `data/docs/`.
- **Tanggapan (`202 Accepted`)**:
  ```json
  {
    "message": "Dokumen diterima dan dijadwalkan untuk pengindeksan",
    "job_id": "job_20261008_143000_1234",
    "filename": "polis-jiwa.pdf",
    "rel_path": "asuransi/polis-jiwa.pdf"
  }
  ```

#### Hapus Dokumen (`DELETE /api/v1/documents/{doc_id}`)
Menghapus rekaman dokumen, seluruh potongan teks terkait, dan vektor dari indeks.

#### Ambil Konten Chunk Lengkap (`GET /api/v1/chunks/{chunk_id}`)
Mengembalikan isi teks utuh dari satu unit potongan dokumen.

---

### 3.6 Pembaruan & Pemantauan Indeks

#### Sinkronisasi Indeks Latar Belakang (`POST /api/v1/index/update`)
Menjadwalkan pemindaian ulang direktori dokumen dan pembaruan indeks inkremental:
- **Tanggapan (`202 Accepted`)**: Jika pekerjaan baru berhasil dijadwalkan.
- **Tanggapan (`409 Conflict`)**: Jika pekerjaan pengindeksan lain sedang berjalan.

#### Status Pengindeksan (`GET /api/v1/index/status`)
Memantau kemajuan sinkronisasi yang sedang atau telah berjalan:
```json
{
  "running": false,
  "last_run": "2026-10-08T14:25:00",
  "progress_pct": 100.0,
  "processed_files": 6,
  "total_files": 6,
  "current_file": null,
  "error": null
}
```

---

## 4. Kode Status HTTP Umum

| Kode Status | Keterangan |
|---|---|
| `200 OK` | Permintaan berhasil diproses. |
| `202 Accepted` | Permintaan diterima dan sedang diproses secara asinkron di latar belakang. |
| `400 Bad Request` | Parameter input tidak valid (misal tipe kueri atau ekstensi berkas tidak didukung). |
| `401 Unauthorized` | API Key tidak disertakan atau tidak cocok saat `API_KEY` dikonfigurasi. |
| `404 Not Found` | Dokumen atau chunk dengan ID yang diminta tidak ditemukan di basis data. |
| `409 Conflict` | Operasi pembaruan indeks bertabrakan dengan pekerjaan indeks yang sedang aktif. |
| `413 Payload Too Large` | Ukuran berkas unggahan melebihi batas `MAX_UPLOAD_MB`. |
| `503 Service Unavailable` | Server Ollama tidak dapat dihubungi atau model yang diminta belum terpasang. |
