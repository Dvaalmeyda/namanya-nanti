# Panduan Konfigurasi Sistem

Seluruh konfigurasi sistem dikelola secara terpusat melalui berkas `app/config.py` menggunakan Pydantic Settings. Parameter dimuat secara otomatis dari berkas `.env` di direktori utama proyek, variabel lingkungan sistem (*environment variables*), atau menggunakan nilai default yang telah ditentukan.

---

## 1. Daftar Parameter Konfigurasi

### 1.1 Konektivitas Ollama

| Variabel | Tipe Data | Nilai Default | Keterangan & Dampak |
|---|---|---|---|
| `OLLAMA_HOST` | `str` | `http://127.0.0.1:11434` | Alamat server Ollama lokal. Hanya menerima alamat loopback jika `ALLOW_REMOTE=false`. |
| `OLLAMA_TIMEOUT_S` | `int` | `300` | Batas waktu tunggu permintaan HTTP ke Ollama dalam detik. |
| `KEEP_ALIVE` | `str` | `30m` | Durasi model dipertahankan dalam memori RAM/VRAM setelah inferensi selesai. |
| `NUM_THREAD` | `Optional[int]` | `None` | Jumlah thread komputasi CPU untuk inferensi. Jika `None`, Ollama mengatur secara otomatis sesuai jumlah core logis. |

---

### 1.2 Model Bahasa (LLM)

| Variabel | Tipe Data | Nilai Default | Keterangan & Dampak |
|---|---|---|---|
| `LLM_MODEL` | `str` | `qwen3:4b-instruct` | Nama model instruksi yang dipanggil di Ollama untuk menjawab pertanyaan. |
| `LLM_THINK` | `bool` | `false` | Menentukan apakah model menjalankan mode penalaran eksplisit (*thinking*). Disetel `false` untuk menghemat latensi dan penggunaan token di CPU. |
| `NUM_CTX` | `int` | `4096` | Ukuran jendela konteks (*context window*) model dalam jumlah token. Mempengaruhi alokasi RAM. |
| `NUM_PREDICT` | `int` | `384` | Batas maksimum token yang dihasilkan oleh model per respons. |
| `TEMPERATURE` | `float` | `0.1` | Nilai keacakan sampling generasi. Nilai rendah dipilih untuk meminimalkan halusinasi pada data faktual. |

---

### 1.3 Model Embedding

| Variabel | Tipe Data | Nilai Default | Keterangan & Dampak |
|---|---|---|---|
| `EMBED_MODEL` | `str` | `bge-m3` | Model embedding untuk representasi vektor dense (dimensi 1024). |
| `EMBED_QUERY_PREFIX` | `str` | `""` | Prefiks teks tambahan untuk kueri pencarian (jika dibutuhkan oleh arsitektur model tertentu). |
| `EMBED_DOC_PREFIX` | `str` | `""` | Prefiks teks tambahan saat memproses potongan dokumen. |
| `EMBED_BATCH` | `int` | `16` | Jumlah potongan teks yang dikirim per batch embedding ke Ollama selama proses pengindeksan. |

---

### 1.4 Loader & Ekstraksi Dokumen

| Variabel | Tipe Data | Nilai Default | Keterangan & Dampak |
|---|---|---|---|
| `PDF_BACKEND` | `str` | `pymupdf` | Backend ekstraktor teks PDF. Menggunakan PyMuPDF (`fitz`). |
| `OCR_MIN_CHARS` | `int` | `50` | Batas minimum karakter per halaman PDF. Jika di bawah nilai ini, halaman diklasifikasikan sebagai pindaian yang membutuhkan OCR. |
| `MAX_FILE_MB` | `int` | `50` | Batas ukuran maksimum berkas dokumen yang diizinkan untuk dibaca (dalam megabyte). |
| `XLSX_ROW_CHUNK` | `int` | `30` | Jumlah baris spreadsheet yang dikelompokkan menjadi satu tabel Markdown per chunk. |

---

### 1.5 Pengindeksan & Penyimpanan

| Variabel | Tipe Data | Nilai Default | Keterangan & Dampak |
|---|---|---|---|
| `CHUNK_SIZE` | `int` | `800` | Target panjang karakter per potongan teks saat pembagian rekursif. |
| `CHUNK_OVERLAP` | `int` | `100` | Jumlah karakter tumpang-tindih antar potongan bersebelahan untuk menjaga kelangsungan konteks. |
| `VECTOR_DTYPE` | `str` | `float32` | Tipe data array biner NumPy untuk penyimpanan vektor di disk. |
| `STEMMER` | `str` | `none` | Jenis stemmer bahasa untuk pencarian FTS5. Default `none` untuk menghindari distorsi kata teknis. |

---

### 1.6 Retrieval & RAG

| Variabel | Tipe Data | Nilai Default | Keterangan & Dampak |
|---|---|---|---|
| `TOP_K` | `int` | `4` | Jumlah potongan teks paling relevan yang dilampirkan ke dalam konteks prompt LLM. |
| `CANDIDATES` | `int` | `20` | Jumlah kandidat teratas yang diambil dari masing-masing metode pencarian (dense dan BM25) sebelum fusi peringkat. |
| `RRF_K` | `int` | `60` | Parameter pemulusan peringkat pada Reciprocal Rank Fusion (RRF). |
| `MIN_DENSE_SCORE` | `float` | `0.35` | Ambang batas kemiripan kosinus minimum pada gerbang penolakan relevansi. |
| `MIN_BM25_SCORE` | `float` | `0.0` | Ambang batas skor leksikal BM25 minimum pada gerbang penolakan relevansi. |
| `MAX_CONTEXT_CHARS` | `int` | `4000` | Batas maksimum panjang total karakter gabungan potongan dokumen yang dimasukkan ke prompt. |
| `HISTORY_TURNS` | `int` | `3` | Jumlah giliran percakapan sebelumnya (*turns*) yang dipertahankan dalam prompt konteks. |
| `HISTORY_MAX_CHARS` | `int` | `1500` | Batas panjang karakter riwayat percakapan yang diizinkan masuk ke prompt. |
| `QUERY_REWRITE` | `bool` | `false` | Mengaktifkan penulisan ulang kueri percakapan via LLM sebelum pencarian. Dinonaktifkan default untuk menghindari penambahan latensi di CPU. |

---

### 1.7 Direktori Penyimpanan

| Variabel | Tipe Data | Nilai Default | Keterangan |
|---|---|---|---|
| `DOCS_DIR` | `Path` | `data/docs` | Direktori penyimpanan berkas dokumen utama milik pengguna. |
| `SAMPLE_DIR` | `Path` | `data/sample` | Direktori berkas dokumen contoh (dummy) untuk pengembangan. |
| `INDEX_DIR` | `Path` | `data/index` | Direktori basis data SQLite (`index.db`) dan array vektor NumPy. |

---

### 1.8 Server REST API (FastAPI)

| Variabel | Tipe Data | Nilai Default | Keterangan & Dampak |
|---|---|---|---|
| `API_HOST` | `str` | `127.0.0.1` | Alamat IP binding server API. Harus loopback jika `ALLOW_REMOTE=false`. |
| `API_PORT` | `int` | `8000` | Port TCP untuk layanan API. |
| `API_KEY` | `str` | `""` | Kunci otentikasi header `X-API-Key`. Jika kosong, autentikasi dinonaktifkan. |
| `WARMUP` | `bool` | `true` | Memuat model ke memori Ollama saat server API pertama kali diinisialisasi (*startup*). |
| `MAX_CONCURRENT_CHAT` | `int` | `1` | Batas jumlah permintaan chat yang diproses bersamaan secara paralel. |
| `MAX_UPLOAD_MB` | `int` | `50` | Batas ukuran unggahan berkas melalui endpoint API. |
| `UPLOAD_SUBDIR` | `str` | `uploads` | Subdirektori di dalam `DOCS_DIR` untuk menampung berkas yang diunggah via API. |

---

### 1.9 Keamanan & Logging

| Variabel | Tipe Data | Nilai Default | Keterangan & Dampak |
|---|---|---|---|
| `ALLOW_REMOTE` | `bool` | `false` | Jika `false`, aplikasi memverifikasi bahwa host Ollama dan API berada di loopback lokal (`127.0.0.1`, `localhost`, `::1`). Jika ada alamat eksternal, startup aplikasi digagalkan. |
| `LOG_CONTENT` | `bool` | `false` | Jika `false`, filter logging menutupi teks dokumen, kueri pengguna, dan jawaban asisten dari keluaran log. |
| `LOG_LEVEL` | `str` | `INFO` | Tingkat keparahan log (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 2. Cara Mengubah Pengaturan

### Menggunakan berkas `.env`
Salin template berkas `.env.example` ke `.env`:

```powershell
Copy-Item .env.example .env
```

Buka `.env` dan perbarui parameter yang diinginkan. Contoh untuk mengubah model LLM dan mengaktifkan autentikasi:

```ini
LLM_MODEL=qwen2.5:1.5b
API_KEY=kunci-rahasia-anda-123
NUM_THREAD=4
```

### Menggunakan Environment Variable di Terminal
Pengaturan variabel lingkungan sistem akan menimpa nilai yang ada pada berkas `.env`:

```powershell
$env:LLM_MODEL = "qwen2.5:1.5b"
$env:TOP_K = "3"
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```
