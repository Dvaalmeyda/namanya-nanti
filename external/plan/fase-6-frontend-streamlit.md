# FASE 6 - Frontend Aplikasi (Streamlit Modular)

> Prasyarat: Fase 4 selesai (API FastAPI berjalan di `http://127.0.0.1:8000`).
> Baca `00-KONTEKS.md` dan `fase-4-api.md` terlebih dahulu.

---

## 1. TUJUAN

Membangun antarmuka pengguna (frontend) berbasis Streamlit yang interaktif, elegan, responsif, dan sepenuhnya modular untuk Personal Document Assistant.

Fitur pembeda utama:
1. **Transparansi Alur Kerja Sistem (Workflow & Trace Log)**: Setiap respons tanya-jawab wajib dilengkapi bagian inspeksi visual yang memperlihatkan runtutan pemrosesan dari awal hingga akhir (kueri gabungan, embedding, dense vs BM25 score, gerbang penolakan, RRF ranking, prompt assembly, token count, hingga profil latensi end-to-end).
2. **Arsitektur Modular Anti "God Files"**: Kode antarmuka dipecah ke dalam modul-modul independen berukuran kecil (masing-masing di bawah 150-200 baris kode). Tidak ada file tunggal raksasa yang menggabungkan logika API, state, layout, dan komponen UI.
3. **Pemisahan Lapisan yang Tegas**: Frontend bertindak murni sebagai klien HTTP/SSE yang mengonsumsi FastAPI backend (`/api/v1`), menjaga isolasi basis data SQLite dan model Ollama tetap terpusat di sisi backend.

---

## 2. ARSITEKTUR DAN STRUKTUR MODUL FRONTEND

### 2.1 Prinsip Desain Modular
- **Single Responsibility Principle**: Setiap modul hanya memiliki satu tanggung jawab (misal: hanya mengurus pemanggilan API obrolan, atau hanya merender kartu sitasi).
- **Stateless Components**: Komponen UI menerima data dari session state dan mengembalikan event atau merender elemen, tanpa menyimpan mutable global state sendiri.
- **Typed Session State**: Seluruh status aplikasi dikelola secara terpusat melalui helper class/dataclass dengan type hints jelas.
- **Ukuran File Terkontrol**: Maksimal 150-200 baris per file untuk kemudahan pemeliharaan dan pengujian unit.

### 2.2 Struktur Direktori (`frontend/`)

```
frontend/
  __init__.py
  app.py                         # Entrypoint tipis (layout utama, navigasi tab/view, inisialisasi state)
  config.py                      # Konfigurasi frontend (API base URL, timeout, interval polling)
  
  client/                        # Lapisan Klien HTTP & SSE (mengonsumsi FastAPI backend)
    __init__.py
    base.py                      # Klien HTTP terpusat dengan error handling dan header auth
    chat_client.py               # Pemanggilan /chat (JSON) dan SSE /chat/stream
    search_client.py             # Pemanggilan /search (retrieval-only)
    document_client.py           # Pemanggilan /documents, /chunks, dan multipart upload
    system_client.py             # Pemanggilan /health dan pemantauan /index/status
    
  state/                         # Manajemen Session State Streamlit
    __init__.py
    session.py                   # Inisialisasi awal dan helper akses st.session_state
    chat_state.py                # Pengelolaan riwayat chat, filter aktif, dan workflow trace log
    
  components/                    # Komponen UI independen dan dapat digunakan ulang
    __init__.py
    header.py                    # Header atas: judul aplikasi dan indikator status backend
    sidebar.py                   # Panel samping: filter folder/tipe berkas, reset obrolan, info model
    chat_bubble.py               # Render balon percakapan pengguna dan asisten
    citation_viewer.py           # Kartu rujukan sitasi [1], [2] dan modal isi teks chunk
    workflow_trace.py            # BAGIAN WAJIB: Visualisasi tahapan alur kerja & metrik per giliran
    system_logs.py               # BAGIAN WAJIB: Penampil log backend waktu nyata (log console viewer)
    metrics_display.py           # Kartu ringkasan latensi (embed_ms, search_ms, ttft, tok/s, total)
    file_uploader.py             # Form unggah berkas multipart dan kartu progres job indexing
    
  views/                         # Halaman / Tampilan Utama
    __init__.py
    chat_view.py                 # Tampilan 1: Tanya-jawab RAG interaktif + panel alur kerja
    search_view.py               # Tampilan 2: Laboratorium Retrieval (komparasi Dense vs BM25 vs Hybrid)
    documents_view.py            # Tampilan 3: Manajemen Dokumen & Pemantau Indeksasi
    system_view.py               # Tampilan 4: Kesehatan Sistem, Model Ollama, dan Konsol Log
    
  utils/                         # Fungsi utilitas pembantu
    __init__.py
    formatters.py                # Pemformat angka latensi, ukuran byte, tanggal, dan status sitasi
    sse_parser.py                # Parser event stream SSE (token, sources, done, error)
```

---

## 3. SPESIFIKASI BAGIAN ALUR PROSES KERJA SISTEM (WORKFLOW TRACE & LOGS)

Bagian ini merupakan **kebutuhan wajib** antarmuka untuk memberikan transparansi penuh atas apa yang terjadi di balik layar sistem RAG lokal.

### 3.1 Rincian 8 Tahap Alur Kerja per Giliran Percakapan

Pada setiap jawaban asisten, disediakan panel lipat (*expander*) berjudul **"Alur Proses Kerja & Log Eksekusi"** yang memuat 8 tahapan terstruktur:

1. **Tahap 1: Query Formulation & History Augmentation**
   - Menampilkan kueri retrieval yang dibentuk sistem (`build_retrieval_query`).
   - Memperlihatkan apakah kueri digabungkan dengan konteks pertanyaan pengguna sebelumnya.

2. **Tahap 2: Dense Query Embedding**
   - Model embedding yang digunakan (misal: `bge-m3`).
   - Durasi waktu embedding kueri (`embed_ms`).
   - Dimensi vektor hasil komputasi (1024 float32).

3. **Tahap 3: Dual Search Execution (Dense + BM25)**
   - Menampilkan pencarian paralel:
     - Dense Search: Kemiripan kosinus terhadap matriks vektor NumPy di memori.
     - Lexical Search: Pencarian kata kunci via SQLite FTS5 (BM25).
   - Menampilkan jumlah kandidat awal yang diambil (`CANDIDATES = 20`).

4. **Tahap 4: Relevance Gate Evaluation (Gerbang Penolakan)**
   - Pengecekan ambang batas relevansi:
     - Skor Dense tertinggi vs `MIN_DENSE_SCORE` (0.35).
     - Skor BM25 tertinggi vs `MIN_BM25_SCORE` (0.0).
   - Status keputusan:
     - `[LOLOS]` jika salah satu atau kedua sinyal relevan.
     - `[DITOLAK: low_relevance]` jika kedua sinyal di bawah ambang batas (proses dihentikan sebelum memanggil LLM).

5. **Tahap 5: Reciprocal Rank Fusion (RRF) & Deduplikasi**
   - Perhitungan bobot RRF dengan rumus `1 / (RRF_K + rank)`.
   - Tabel komparasi kandidat chunk:
     - Kolom: Dokumen, Lokasi, Skor Dense, Skor BM25, Skor RRF, Rank Akhir.
   - Deteksi dokumen kembar: status `also_in` jika dokumen yang sama berada di beberapa path.
   - Pemotongan kuota konteks maksimum (`MAX_CONTEXT_CHARS = 4000`).

6. **Tahap 6: Prompt Assembly & Context Injection**
   - Rangkuman potongan dokumen terpilih (`TOP_K = 4`) yang diinjeksi ke dalam format prompt sitasi `[1]`, `[2]`.
   - Estimasi jumlah token prompt (`prompt_tokens`).

7. **Tahap 7: LLM Inference & Token Generation**
   - Model LLM yang digunakan (misal: `qwen3:4b-instruct`).
   - Profil latensi generasi:
     - Waktu prefill prompt (`prefill_ms`).
     - Waktu hingga token pertama (`ttft_ms`).
     - Waktu generasi token (`generate_ms`).
     - Throughput kecepatan generasi (`tokens_per_s`).
     - Jumlah token output (`completion_tokens`).

8. **Tahap 8: Post-processing Sitasi & Verifikasi**
   - Ekstraksi nomor sitasi dari teks jawaban (`parse_citations`).
   - Klasifikasi sitasi:
     - `[DIRUJUK]` untuk sumber yang benar-benar dikutip dalam teks jawaban.
     - `[TIDAK DIRUJUK]` untuk sumber yang masuk konteks tetapi tidak dikutip oleh LLM.
   - Pengecekan penolakan konteks akhir (`not_in_context`).

### 3.2 Tampilan Log Konsol Sistem Real-Time (System Log Viewer)
- Menampilkan tab tersendiri di halaman sistem untuk membaca isi `data/index/app.log`.
- Filter berdasarkan level log: `ALL`, `INFO`, `WARNING`, `ERROR`.
- Opsi pencarian teks log dan tombol refresh manual / auto-refresh interval 5 detik.
- Menampilkan status sensor privasi (`[REDACTED]`) sesuai aturan keamanan lokal.

---

## 4. RINCIAN TAMPILAN ANTARMUKA (VIEWS)

### 4.1 Tampilan 1: Asisten Obrolan (`chat_view.py`)
- **Area Pesan**: Percakapan multi-turn yang rapi.
- **Mode Eksekusi**: Pilihan tombol atau toggle antara mode Streaming (SSE token-demi-token) dan Non-Streaming (JSON utuh).
- **Penanganan Sitasi**: Setiap nomor sitasi `[1]`, `[2]` dapat diklik untuk membuka ringkasan lokasi dokumen, skor relevansi, dan isi potongan teks lengkap.
- **Panel Alur Kerja (Workflow Trace)**: Berada tepat di bawah setiap jawaban asisten dalam bentuk kontainer lipat (*expander*).
- **Sidebar**:
  - Filter Folder (dinamis berdasarkan folder yang ada di basis data).
  - Filter Tipe Berkas (`pdf`, `docx`, `xlsx`, `md`, `txt`).
  - Pengaturan nilai `TOP_K` (slider 1 - 10).
  - Tombol "Hapus Riwayat Percakapan".

### 4.2 Tampilan 2: Laboratorium Retrieval (`search_view.py`)
- Khusus untuk menguji pencarian murni tanpa LLM (mengonsumsi `POST /api/v1/search`).
- Pilihan mode: `Hybrid (RRF)`, `Dense Only (BGE-M3)`, `BM25 Only (FTS5)`.
- Input kueri pencarian dan filter folder/ekstensi.
- Hasil pencarian berupa tabel interaktif:
  - Peringkat, Dokumen, Cuplikan Teks, Skor Dense, Skor BM25, Skor RRF.
- Metrik waktu: `embed_ms` dan `search_ms`.

### 4.3 Tampilan 3: Manajemen Dokumen & Indeksasi (`documents_view.py`)
- **Status Indeks Berjalan**: Kartu status yang menampilkan apakah pekerjaan sinkronisasi indeks sedang `idle`, `running`, `completed`, atau `failed`.
- **Progress Bar & ETA**: Jika job sedang berjalan, progress bar dan estimasi sisa waktu diperbarui secara berkala via polling `GET /api/v1/index/status`.
- **Form Unggah Berkas**:
  - Mengunggah berkas (`.pdf`, `.docx`, `.xlsx`, `.md`, `.txt`).
  - Pemilihan folder tujuan di dalam `data/docs/`.
  - Pemicu otomatis pekerjaan sinkronisasi indeks setelah berkas terunggah.
- **Tabel Dokumen Terindeks**:
  - Daftar dokumen: Nama berkas, Jalur direktori, Ukuran berkas, Jumlah chunk, Status OCR, Waktu indeks.
  - Tombol aksi: "Lihat Chunk" dan "Hapus Dokumen" (dengan konfirmasi).

### 4.4 Tampilan 4: Status Sistem & Konsol Log (`system_view.py`)
- **Indikator Kesehatan**:
  - Status koneksi Ollama (`ok` / `terputus`).
  - Model Ollama yang terpasang dan yang sedang aktif di RAM/VRAM.
  - Versi indeks basis data SQLite, total dokumen, dan total chunk.
- **Konsol Log**:
  - Tampilan teks log `app.log` dengan scroll internal dan penyorotan level log.

---

## 5. DEPENDENSI DAN INTEGRASI PROYEK

### 5.1 Perubahan pada `pyproject.toml`
Tambahkan dependensi berikut ke dalam `pyproject.toml`:
- `streamlit>=1.32.0` (antarmuka web)
- Pindahkan `httpx>=0.27.0` dari `dependency-groups.dev` ke `dependencies` utama (klien HTTP/SSE backend)

### 5.2 Perintah Eksekusi
Aplikasi dijalankan dalam dua proses independen:
1. **Backend API**:
   ```powershell
   uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 1
   ```
2. **Frontend Streamlit**:
   ```powershell
   uv run streamlit run frontend/app.py --server.port 8501 --server.address 127.0.0.1
   ```

---

## 6. TAHAPAN PENGERJAAN (STEP-BY-STEP IMPLEMENTATION)

Pengerjaan dibagi ke dalam 5 sub-tahap berurutan:

### Sub-tahap 6.1: Pondasi, Konfigurasi, dan API Client
- Perbarui `pyproject.toml` dengan `streamlit` dan `httpx`.
- Buat `frontend/config.py` untuk mengelola konfigurasi koneksi (`BACKEND_API_URL = "http://127.0.0.1:8000/api/v1"`).
- Buat modul `frontend/client/`:
  - `base.py`: Wrapper HTTP dengan penanganan koneksi gagal dan status HTTP 503/404/409.
  - `system_client.py`: Pemeriksaan health dan status job.
  - `document_client.py`: Pengambilan daftar dokumen dan multipart upload.
  - `search_client.py`: Pengambilan hasil pencarian retrieval.
  - `chat_client.py`: Pemanggilan `/chat` JSON dan parsing aliran SSE `/chat/stream`.

### Sub-tahap 6.2: State Management & Parsing SSE
- Buat `frontend/utils/sse_parser.py`: Parser stream event `token`, `sources`, `done`, `error`.
- Buat `frontend/state/session.py` dan `frontend/state/chat_state.py`:
  - Mengatur struktur riwayat pesan: `role`, `content`, `sources`, `refused`, `timing`, `workflow_trace`.
  - Mengatur filter pencarian yang sedang dipilih pengguna.

### Sub-tahap 6.3: Komponen Reusable UI
- Buat `frontend/components/header.py`: Bar atas dengan status koneksi backend.
- Buat `frontend/components/sidebar.py`: Kontrol filter metadata, top_k, dan tombol pembersih sesi.
- Buat `frontend/components/chat_bubble.py`: Bubble pesan dengan format sitasi.
- Buat `frontend/components/citation_viewer.py`: Kartu informasi sitasi dan isi teks potongan dokumen.
- Buat `frontend/components/metrics_display.py`: Widget visualisasi latensi.
- Buat `frontend/components/workflow_trace.py`: **Komponen utama visualisasi 8 tahap alur kerja sistem**.
- Buat `frontend/components/system_logs.py`: Penampil berkas log backend.
- Buat `frontend/components/file_uploader.py`: Komponen unggah berkas dan indikator progres.

### Sub-tahap 6.4: Perakitan Views (Halaman)
- Buat `frontend/views/chat_view.py`: Antarmuka tanya-jawab lengkap dengan panel alur kerja terintegrasi.
- Buat `frontend/views/search_view.py`: Antarmuka pengujian retrieval murni.
- Buat `frontend/views/documents_view.py`: Antarmuka dokumen dan manajemen indeks.
- Buat `frontend/views/system_view.py`: Antarmuka diagnosa sistem dan konsol log.
- Buat `frontend/app.py`: Entrypoint perakitan seluruh tampilan dengan sistem navigasi tab Streamlit.

### Sub-tahap 6.5: Pengujian, Polish, dan Dokumentasi
- Uji alur obrolan non-streaming dan streaming.
- Uji kelengkapan informasi pada panel alur kerja (apakah seluruh metrik dan tahap tampil akurat).
- Uji skenario kesalahan:
  - Backend FastAPI belum menyala (menampilkan pesan ramah pengguna).
  - Ollama belum aktif (tampilkan petunjuk penanganan 503).
  - Unggah berkas format salah atau path traversal (tampilkan pesan validasi).
- Perbarui dokumentasi petunjuk menjalankan frontend di `README.md`.

---

## 7. BATASAN TEKNIS

- Frontend tidak boleh mengakses langsung basis data SQLite (`index.db`) atau memanggil model Ollama secara lokal. Seluruh I/O wajib melalui REST API FastAPI.
- Tidak menggunakan emoticon/emoji pada teks, label tombol, atau status UI (gunakan penanda teks standar seperti `[OK]`, `[INFO]`, `[ERROR]`, `[RUNNING]`).
- Ukuran kode tiap berkas tidak boleh melebihi 200 baris kode untuk mencegah munculnya file monolitik ("god files").
- Frontend berjalan hanya pada antarmuka lokal loopback (`127.0.0.1:8501`).

---

## 8. KRITERIA SELESAI

- Seluruh kode berada dalam struktur modular di direktori `frontend/` tanpa file melebihi 200 baris.
- Antarmuka Streamlit berjalan mulus tanpa error saat dieksekusi dengan `uv run streamlit run frontend/app.py`.
- Bagian alur proses kerja sistem (workflow trace) menampilkan rincian tahapan yang jelas pada setiap jawaban:
  - Kueri retrieval yang dibentuk.
  - Waktu embedding dense.
  - Skor kandidat Dense vs BM25.
  - Status evaluasi gerbang penolakan.
  - Hasil perangkingan RRF dan pemotongan konteks.
  - Waktu prefill, generate, throughput (tok/s), dan sitasi terverifikasi.
- Tab konsol log menampilkan isi log backend `app.log` secara akurat.
- Unggah dokumen, pemantauan indeks, dan pencarian retrieval berfungsi terhubung langsung dengan backend FastAPI.
