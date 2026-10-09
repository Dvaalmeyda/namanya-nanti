# FASE 7 - Kontainerisasi Aplikasi (Docker & Docker Compose)

> Prasyarat: Fase 4 (API FastAPI) dan Fase 6 (Frontend Streamlit) telah selesai dan berfungsi dengan baik.
> Baca `00-KONTEKS.md` terlebih dahulu sebelum memulai implementasi.

---

## 1. TUJUAN DAN ANALISIS MASALAH

### 1.1 Masalah Setup Manual Saat Ini
Saat ini, pengguna baru yang ingin menjalankan Personal Document Assistant harus melalui proses instalasi dan konfigurasi lokal yang panjang dan rumit:
1. Menginstal Python 3.11+.
2. Menginstal package manager `uv`.
3. Menginstal aplikasi desktop Ollama secara terpisah.
4. Mengonfigurasi variabel lingkungan sistem operasi (misalnya pengaturan thread dan mode CPU untuk Ollama).
5. Menjalankan daemon `ollama serve`.
6. Menjalankan `uv sync` untuk mengunduh belasan pustaka Python.
7. Menyalin dan menyesuaikan berkas `.env` dari `.env.example`.
8. Menjalankan perintah unduh model: `ollama pull bge-m3` (sekitar 1,2 GB).
9. Menjalankan perintah unduh model: `ollama pull qwen3:4b-instruct` (sekitar 2,5 GB).
10. Menjalankan skrip inisialisasi dummy docs (`scripts/make_sample_docs.py`).
11. Membuka terminal pertama untuk menjalankan server backend FastAPI (`uvicorn app.api.main:app`).
12. Membuka terminal kedua untuk menjalankan antarmuka Streamlit (`streamlit run frontend/app.py`).

Rangkaian langkah manual ini rentan terhadap kesalahan konfigurasi lingkungan (environment mismatch), bentrok port, kendala path eksekusi, serta membebani pengguna non-teknis.

### 1.2 Sasaran Kontainerisasi
Tujuan utama dari Fase 7 adalah menyediakan pengalaman *zero-friction setup* dan *one-command launch*:
- Seluruh dependensi (Ollama, Python, FastAPI, Streamlit, dan model AI) dikemas ke dalam kontainer Docker yang terisolasi.
- Pengguna hanya perlu menjalankan satu perintah (`docker compose up -d`) atau mengeklik skrip launcher.
- Pengunduhan model awal (`bge-m3` dan `qwen3:4b-instruct`) ditangani secara otomatis pada saat inisialisasi awal tanpa perlu perintah manual.
- Penyimpanan dokumen (`data/docs`), indeks pencarian (`data/index`), dan cache model Ollama bersifat persisten sehingga data tidak hilang saat kontainer dimatikan atau diperbarui.
- Disediakan opsi fleksibel: menjalankan Ollama di dalam kontainer secara penuh, atau menyambungkan kontainer backend ke Ollama yang sudah terpasang di host.

---

## 2. ARSITEKTUR LAYANAN (DOCKER COMPOSE)

Sistem disusun menggunakan Docker Compose dengan pemisahan tanggung jawab (*one process per container*) yang terhubung melalui *user-defined bridge network*.

```
+------------------------------------------------------------------------------------+
|                               HOST MACHINE (USER)                                  |
|                                                                                    |
|   Browser: http://localhost:8501 (UI)   |   Swagger: http://localhost:8000/docs    |
|   Folder Dokumen: ./data/docs           |   Database: ./data/index                 |
+------------------------------------------------------------------------------------+
                                      |
                                      v
+----------------------------- DOCKER NETWORK (pda-net) -----------------------------+
|                                                                                    |
|  +--------------------+       +--------------------+       +--------------------+  |
|  |     frontend       | ----> |      backend       | ----> |       ollama       |  |
|  |   (Streamlit UI)   |       |     (FastAPI)      |       |  (Inference CPU)   |  |
|  |     Port: 8501     |       |     Port: 8000     |       |    Port: 11434     |  |
|  +--------------------+       +--------------------+       +--------------------+  |
|                                         |                            ^             |
|                                         |                            |             |
|                                         |                  +--------------------+  |
|                                         +----------------- |    model-puller    |  |
|                                                            | (Auto-pull init)   |  |
|                                                            +--------------------+  |
+------------------------------------------------------------------------------------+
```

### 2.1 Rincian Layanan

1. **Layanan `ollama`**:
   - Citra: `ollama/ollama:latest`.
   - Peran: Server inferensi lokal untuk embedding (`bge-m3`) dan LLM (`qwen3:4b-instruct`).
   - Mode inferensi default: CPU (konsisten dengan arsitektur proyek saat ini).
   - Port: `11434:11434` (diekspos ke host agar transparan untuk inspeksi opsional).
   - Volume: `ollama_models:/root/.ollama` (penyimpanan model agar tidak diunduh ulang).
   - Healthcheck: Memverifikasi kesiapan port HTTP Ollama sebelum layanan berikutnya aktif.

2. **Layanan `model-puller` (Inisialisasi Otomatis)**:
   - Citra: `ollama/ollama:latest`.
   - Peran: Memastikan model yang dibutuhkan (`bge-m3` dan `qwen3:4b-instruct`) sudah terunduh sebelum backend mulai bekerja.
   - Perilaku:
     - Berjalan sekali saat startup (`restart: "no"`).
     - Menunggu hingga `ollama` dinyatakan sehat (`service_healthy`).
     - Mengecek ketersediaan model via CLI/API. Jika belum ada, melakukan `pull`.
     - Keluar dengan kode 0 setelah selesai.

3. **Layanan `backend`**:
   - Citra: Dibangun dari target `backend` pada multi-stage `Dockerfile`.
   - Peran: Menjalankan API FastAPI, orkestrasi RAG, chunking, hybrid retrieval, dan pengelolaan basis data SQLite.
   - Port: `8000:8000`.
   - Lingkungan:
     - `OLLAMA_HOST=http://ollama:11434`
     - `ALLOW_REMOTE=true` (diperlukan karena nama host kontainer `ollama` bukan IP loopback literal).
     - `API_HOST=0.0.0.0`
     - `API_PORT=8000`
     - `DOCS_DIR=/app/data/docs`
     - `INDEX_DIR=/app/data/index`
     - `SAMPLE_DIR=/app/data/sample`
     - `WARMUP=true`
   - Volume:
     - Bind mount `./data/docs:/app/data/docs` (agar pengguna bisa langsung memasukkan berkas dari host).
     - Bind mount `./data/index:/app/data/index` (agar database `index.db` tetap tersimpan di host).
   - Dependensi urutan (*startup order*): Menunggu `ollama` sehat dan `model-puller` selesai dengan sukses (`service_completed_successfully`).
   - Healthcheck: `GET /api/v1/health` mengembalikan status HTTP 200.

4. **Layanan `frontend`**:
   - Citra: Dibangun dari target `frontend` pada multi-stage `Dockerfile`.
   - Peran: Menjalankan antarmuka Streamlit modular (Chat RAG, Retrieval Lab, Documents View, System View).
   - Port: `8501:8501`.
   - Lingkungan:
     - `PDA_API_URL=http://backend:8000/api/v1`
     - `STREAMLIT_SERVER_PORT=8501`
     - `STREAMLIT_SERVER_ADDRESS=0.0.0.0`
     - `STREAMLIT_SERVER_HEADLESS=true`
   - Dependensi urutan: Menunggu `backend` sehat (`service_healthy`).
   - Healthcheck: Memeriksa endpoint internal `/_stcore/health` milik Streamlit.

---

## 3. DESAIN DOCKERFILE MULTI-STAGE

Untuk menghemat ukuran citra, mempercepat proses build, dan memanfaatkan cache layer secara maksimal, backend dan frontend disatukan dalam satu berkas `Dockerfile` multi-stage menggunakan tool `uv`.

### 3.1 Struktur Tahapan Build

1. **Tahap 1 (`base`)**:
   - Menggunakan `python:3.11-slim-bookworm` sebagai base image yang ringan dan stabil.
   - Menginstal `curl` (untuk healthcheck).
   - Menyalin binary `uv` dari citra resmi `ghcr.io/astral-sh/uv:latest`.
   - Mengatur environment variable optimal Python (`PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`, `UV_COMPILE_BYTECODE=1`).

2. **Tahap 2 (`builder`)**:
   - Menyalin berkas definisi dependensi: `pyproject.toml` dan `uv.lock`.
   - Menjalankan `uv sync --frozen --no-dev --no-install-project` untuk memasang semua pustaka ke virtualenv `/app/.venv`.
   - Mengisolasi lapisan download pustaka dari perubahan kode aplikasi.

3. **Tahap 3 (`runtime`)**:
   - Membuat pengguna non-root `appuser` (keamanan kontainer sesuai best practice).
   - Menyalin virtualenv `/app/.venv` dari tahap `builder`.
   - Mengaktifkan PATH virtualenv ke dalam environment.
   - Menyalin kode sumber aplikasi (`app/`, `frontend/`, `scripts/`, `data/sample/`).
   - Menyiapkan folder `data/docs` dan `data/index` dengan izin akses yang tepat untuk `appuser`.

4. **Tahap 4 (`backend`)**:
   - Target build untuk layanan FastAPI.
   - Expose port `8000`.
   - Menjalankan perintah:
     `CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]`

5. **Tahap 5 (`frontend`)**:
   - Target build untuk antarmuka Streamlit.
   - Expose port `8501`.
   - Menjalankan perintah:
     `CMD ["streamlit", "run", "frontend/app.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true"]`

### 3.2 Optimasi Melalui `.dockerignore`
Berkas `.dockerignore` wajib mencakup:
- `.venv/`, `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`
- `.git/`, `.gitignore`
- `.pytest_cache/`, `tests/`, `eval/reports/`
- `.agents/`, `.gemini/`
- `data/docs/*` (kecuali placeholder jika ada)
- `data/index/*`
- `*.log`

Hal ini memastikan konteks build berukuran sangat kecil (di bawah 5 MB) dan build berjalan dalam hitungan detik.

---

## 4. SKENARIO PENGGUNAAN FLEKSIBEL

Terdapat dua profil pengguna utama yang harus diakomodasi:

### 4.1 Skenario A: Full Docker (Pengguna Baru / Zero Setup)
- Pengguna belum memiliki Ollama di komputernya.
- Pengguna hanya menjalankan:
  ```powershell
  docker compose up -d
  ```
- Docker akan otomatis mengunduh Ollama, mengunduh model `bge-m3` dan `qwen3:4b-instruct`, menyalakan backend, dan menyalakan frontend.
- Pengguna langsung membuka peramban di `http://localhost:8501`.

### 4.2 Skenario B: Host-Ollama Mode (Pengguna yang Sudah Memiliki Model di Komputer)
- Pengguna sudah memiliki Ollama native yang berjalan di komputer host (misalnya di Windows dengan GPU atau model yang sudah pernah diunduh).
- Menghindari pengunduhan ulang file model sebesar 3,7 GB ke dalam Docker volume.
- Disediakan profil atau konfigurasi override:
  - Menyambungkan `OLLAMA_HOST` ke `http://host.docker.internal:11434`.
  - Melewati layanan `ollama` dan `model-puller` di kontainer menggunakan Docker Compose profile (`--profile full` vs default).

---

## 5. PENYESUAIAN KODE DAN PRIVASI

### 5.1 Catatan Penting Mengenai `ALLOW_REMOTE`
Di dalam modul `app/privacy.py`, fungsi `assert_local_only()` memvalidasi host koneksi Ollama:
```python
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
```
Ketika backend berjalan di dalam jaringan Docker dan menghubungi layanan `ollama`, hostname yang digunakan adalah `ollama` (atau `host.docker.internal` pada mode host).
Oleh karena itu:
- Variabel lingkungan `ALLOW_REMOTE=true` **wajib diatur** pada konfigurasi kontainer backend.
- Pengaturan ini aman karena koneksi tetap berada di dalam jaringan virtual Docker pribadi dan tidak keluar ke internet publik.

---

## 6. STRUKTUR BERKAS YANG AKAN DIBUAT

```
e:\diva\ai engineer\
├── Dockerfile                  # Multi-stage build (base, builder, runtime, backend, frontend)
├── .dockerignore               # Pengecualian berkas dari konteks build
├── docker-compose.yml          # Definisi multi-container (ollama, model-puller, backend, frontend)
├── docker-compose.override.yml # Template opsional (misal: mode Host Ollama)
├── .env.docker                 # Template variabel lingkungan siap pakai untuk Docker
├── scripts/
│   ├── docker-init-models.sh   # Skrip inisialisasi pengunduhan model di kontainer init
│   ├── docker-start.bat        # Skrip 1-klik untuk pengguna Windows
│   └── docker-start.sh         # Skrip 1-klik untuk pengguna Linux/macOS
└── README.md                   # Pembaruan petunjuk instalasi menggunakan Docker
```

---

## 7. TAHAPAN EKSEKUSI IMPLEMENTASI

Implementasi kontainerisasi ini dibagi menjadi 6 tahap terstruktur:

### Tahap 1: Pembuatan `.dockerignore`
- Mengonfigurasi seluruh pola berkas dan folder yang tidak boleh masuk ke build context Docker.
- Memverifikasi ukuran build context.

### Tahap 2: Pembuatan Multi-Stage `Dockerfile`
- Menulis tahapan `base`, `builder`, `runtime`, `backend`, dan `frontend`.
- Memastikan instalasi dependensi menggunakan `uv` non-interaktif dan terkompilasi bytecode.
- Menetapkan izin non-root user `appuser`.

### Tahap 3: Pembuatan Skrip Pengunduh Model (`scripts/docker-init-models.sh`)
- Menulis logika pengecekan ketersediaan model pada server Ollama (`bge-m3` dan `qwen3:4b-instruct`).
- Menjalankan `ollama pull` hanya jika model belum terdaftar di `ollama list`.

### Tahap 4: Pembuatan `docker-compose.yml`
- Mengonfigurasi keempat layanan beserta dependensi, jaringan, dan volume persisten.
- Mengatur healthcheck pada masing-masing layanan dengan interval dan timeout yang wajar.
- Menyusun mapping port `8000` (API) dan `8501` (UI).
- Mengonfigurasi volume `ollama_models`, `./data/docs`, dan `./data/index`.

### Tahap 5: Pembuatan Skrip Launcher 1-Klik
- Menulis `docker-start.bat` untuk lingkungan Windows:
  - Memeriksa apakah Docker Desktop sedang berjalan.
  - Menjalankan `docker compose up -d`.
  - Menunggu hingga frontend siap, lalu secara otomatis membuka peramban ke `http://localhost:8501`.
- Menulis `docker-stop.bat` untuk mematikan layanan dengan tertib (`docker compose down`).

### Tahap 6: Dokumentasi dan Pembaruan Panduan Pengguna
- Menambahkan bab khusus "Instalasi dan Menjalankan Melalui Docker" pada `README.md`.
- Membandingkan opsi instalasi manual vs Docker sehingga pengguna memiliki panduan yang jelas.

---

## 8. KRITERIA SELESAI DAN PENGUJIAN VALIDASI

Implementasi kontainerisasi dinyatakan selesai apabila memenuhi seluruh kriteria pengujian berikut:

1. **Uji Build**:
   - `docker compose build` berhasil tanpa error dan menghasilkan image `backend` serta `frontend`.
   - Ukuran image terkontrol dan memanfaatkan layer cache dengan optimal.

2. **Uji Inisialisasi Otomatis (Cold Start)**:
   - Saat dijalankan pada keadaan volume bersih (`docker compose up -d`), kontainer `ollama` aktif, diikuti oleh `model-puller` yang mengunduh `bge-m3` dan `qwen3:4b-instruct`.
   - Kontainer `backend` baru aktif setelah model selesai diunduh dan warm-up berjalan sukses.
   - Kontainer `frontend` aktif dan dapat diakses di `http://localhost:8501`.

3. **Uji Fungsional End-to-End**:
   - Buka `http://localhost:8501`.
   - Buka tab "System": status backend dan Ollama menunjukkan indikator sehat (model `bge-m3` dan `qwen3:4b-instruct` terdeteksi).
   - Unggah dokumen uji (PDF/TXT) via tab "Documents".
   - Verifikasi bahwa proses indexing latar belakang selesai.
   - Ajukan pertanyaan di tab "Chat RAG": jawaban, sitasi, dan alur kerja (workflow trace) ditampilkan secara tepat.

4. **Uji Persistensi Data**:
   - Matikan kontainer dengan `docker compose down`.
   - Nyalakan kembali dengan `docker compose up -d`.
   - Verifikasi bahwa:
     - Model Ollama tidak diunduh ulang (volume cache tersimpan).
     - Dokumen dan indeks yang telah dibuat sebelumnya tetap terbaca di frontend tanpa perlu re-indexing.

5. **Uji Penanganan Sumber Daya dan Keamanan**:
   - Kontainer backend dan frontend berjalan sebagai pengguna non-root.
   - Tidak ada kebocoran port yang tidak diperlukan di luar host loopback.
   - Penutupan kontainer melalui `SIGTERM` ditangani secara elegan (graceful shutdown).
