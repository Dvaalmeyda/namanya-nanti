# Personal Document Assistant

Aplikasi tanya-jawab atas dokumen pribadi berbasis Retrieval-Augmented Generation (RAG). Pengguna mengunggah atau menempatkan dokumen (PDF, DOCX, XLSX, Markdown, TXT), sistem mengindeksnya, lalu menjawab pertanyaan berdasarkan isi dokumen beserta rujukan sumbernya. Seluruh komponen (model bahasa, model embedding, indeks, API) dijalankan di perangkat pengguna melalui Ollama dan FastAPI.

Versi saat ini: **0.2.0** (lihat [CHANGELOG.md](CHANGELOG.md)).

> Data pada repositori ini adalah **data dummy**. Seluruh dokumen di `data/sample/` dan seluruh pertanyaan di `eval/golden.sample.jsonl` dibuat oleh skrip untuk keperluan pengembangan dan pengujian. Tidak ada dokumen pribadi nyata di dalam repositori.

## Daftar Isi

1. [Overview Sistem](#1-overview-sistem)
2. [Fungsi Utama dan Fitur](#2-fungsi-utama-dan-fitur)
3. [Model yang Digunakan](#3-model-yang-digunakan)
4. [Spesifikasi Perangkat dan Performa](#4-spesifikasi-perangkat-dan-performa)
5. [Struktur Proyek](#5-struktur-proyek)
6. [Setup dan Menjalankan Proyek](#6-setup-dan-menjalankan-proyek)
7. [Penggunaan API](#7-penggunaan-api)
8. [Data yang Digunakan](#8-data-yang-digunakan)
9. [Pengujian dan Evaluasi](#9-pengujian-dan-evaluasi)
10. [Keterbatasan](#10-keterbatasan)
11. [Rekomendasi Upgrade](#11-rekomendasi-upgrade)
12. [Dokumentasi Lanjutan](#12-dokumentasi-lanjutan)

---

## 1. Overview Sistem

Sistem terdiri dari lima lapisan:

| Lapisan | Peran | Implementasi |
|---|---|---|
| Ingest | Membaca dokumen, memecah menjadi chunk, membuat embedding | `app/loaders.py`, `app/indexing.py` |
| Penyimpanan | Menyimpan teks, metadata, vektor, dan indeks pencarian kata kunci | SQLite (tabel biasa + FTS5), `app/store.py` |
| Retrieval dan RAG | Pencarian hybrid, penyaringan relevansi, penyusunan prompt, pemanggilan LLM, pengolahan sitasi | `app/retrieval.py`, `app/rag.py`, `app/prompts.py` |
| Antarmuka API | REST API dengan dokumentasi Swagger UI dan ReDoc | FastAPI, `app/api/` |
| Antarmuka Web | Antarmuka grafis modular untuk pengguna di peramban | Streamlit, `frontend/` |

Alur permintaan tanya-jawab:

```
Pertanyaan --> embedding query --> pencarian dense (vektor) + BM25 (FTS5)
           --> penggabungan peringkat (Reciprocal Rank Fusion)
           --> penyaringan relevansi (jika skor di bawah ambang: ditolak tanpa memanggil LLM)
           --> penyusunan prompt (konteks dokumen + riwayat percakapan)
           --> LLM (Ollama) --> jawaban + sitasi [n] + metadata sumber
```

Penjelasan lebih rinci ada di [docs/architecture.md](docs/architecture.md).

## 2. Fungsi Utama dan Fitur

Fungsi utama: menjawab pertanyaan pengguna berdasarkan isi dokumen yang telah diindeks, disertai rujukan ke dokumen dan lokasi asalnya (halaman, bab, atau sheet).

Fitur yang tersedia pada versi 0.2.0:

- **Antarmuka Web Streamlit Modular**: antarmuka pengguna interaktif yang terhubung murni melalui REST API (bebas akses basis data langsung), memuat chat RAG interaktif (streaming SSE dan non-streaming JSON), laboratorium retrieval, manajemen dokumen dan inspeksi chunk, serta pemantauan log server real-time.
- **Transparansi Alur Kerja (Workflow Trace 8 Tahap)**: visualisasi langkah inferensi RAG per tanggapan (kueri, filter, embedding, hybrid search, relevance gate, penyusunan prompt, generasi LLM, sitasi).
- **Format dokumen**: PDF (PyMuPDF), DOCX (python-docx), XLSX (openpyxl, dipecah per kelompok baris), Markdown, dan TXT. PDF hasil pemindaian terdeteksi dan ditandai membutuhkan OCR (OCR belum diimplementasikan).
- **Pengindeksan inkremental**: perubahan dideteksi lewat hash berkas; dokumen yang tidak berubah tidak diproses ulang. Dokumen kembar (isi sama, path berbeda) berbagi embedding.
- **Pencarian hybrid**: kombinasi pencarian vektor (dense) dan BM25 melalui Reciprocal Rank Fusion. Mode `dense` dan `bm25` juga dapat dipilih secara terpisah.
- **Filter metadata**: berdasarkan folder, tipe berkas, atau ID dokumen.
- **Penyaringan relevansi**: pertanyaan dengan skor kemiripan rendah ditolak dengan pesan standar tanpa memanggil LLM.
- **Sitasi**: jawaban memuat penanda `[1]`, `[2]`, dan seterusnya yang dipetakan ke metadata sumber.
- **Riwayat percakapan**: pertanyaan lanjutan memakai beberapa giliran terakhir dari riwayat yang dikirim klien. Server tidak menyimpan sesi.
- **Perlindungan terhadap prompt injection**: teks dokumen diperlakukan sebagai data dan dibungkus dalam penanda khusus pada prompt.
- **REST API**: endpoint untuk chat (JSON dan streaming SSE), pencarian, manajemen dokumen, pembaruan indeks di latar belakang, diagnostik log sistem, dan health check.
- **Autentikasi opsional**: header `X-API-Key` jika `API_KEY` diisi.
- **Kontrol privasi**: koneksi ke host Ollama selain loopback ditolak kecuali `ALLOW_REMOTE=true`; isi dokumen dan pertanyaan tidak dicatat ke log kecuali `LOG_CONTENT=true`.
- **Modul evaluasi**: golden set, metrik retrieval dan jawaban, sweep parameter, dan runner end-to-end (`eval/`).

## 3. Model yang Digunakan

Semua model dijalankan melalui Ollama.

| Peran | Model | Ukuran unduhan | Keterangan |
|---|---|---|---|
| LLM default | `qwen3:4b-instruct` | sekitar 2,5 GB | Mode non-thinking (`LLM_THINK=false`) |
| LLM pembanding | `qwen2.5:1.5b` | sekitar 1 GB | Dipakai pada evaluasi komparatif |
| Embedding | `bge-m3` | sekitar 1,2 GB | Multi-bahasa, dipakai untuk dokumen dan query |

Parameter generasi default: `NUM_CTX=4096`, `NUM_PREDICT=384`, `TEMPERATURE=0.1`. Daftar lengkap parameter ada di [docs/configuration.md](docs/configuration.md).

## 4. Spesifikasi Perangkat dan Performa

### Perangkat yang dipakai untuk pengembangan dan pengukuran

| Komponen | Spesifikasi |
|---|---|
| CPU | Intel Core i7-1165G7 (4 core, 8 thread) |
| RAM | 16 GB |
| GPU | NVIDIA GeForce MX450 (2 GB VRAM), **tidak digunakan** |
| Sistem operasi | Windows 11 |
| Mode inferensi | CPU saja (`OLLAMA_VULKAN=0`, `CUDA_VISIBLE_DEVICES=-1`) |
| Python | 3.11 atau lebih baru (diuji pada 3.13) |

GPU tidak digunakan karena runner Ollama gagal dengan error `llama-server process has terminated: exit status 0xe06d7363` pada konfigurasi GPU tersebut.

### Hasil pengukuran

Pengukuran dilakukan pada 8 Oktober 2026 menggunakan 20 pertanyaan dummy dengan `TOP_K=4`. Angka bersifat spesifik untuk perangkat, model, dan dataset di atas, dan akan berbeda pada kondisi lain.

**Evaluasi end-to-end (RAG lengkap)**

| Metrik | `qwen3:4b-instruct` | `qwen2.5:1.5b` |
|---|---|---|
| Pass rate (run 2) | 95% (19/20) | 95% (19/20) |
| Pass rate (run 3, setelah koreksi golden set) | 100% (20/20) | belum dijalankan ulang |
| Hit@4 | 100% | 100% |
| MRR | 1,00 | 1,00 |
| Kecepatan generasi rata-rata | 5,8 sampai 6,2 token/detik | 6,2 token/detik |
| Durasi total rata-rata per pertanyaan | 13,8 sampai 14,0 detik | 13,4 detik |
| Pertanyaan di luar dokumen yang ditolak | 3/3 | 3/3 |
| Percobaan prompt injection yang tidak membocorkan instruksi | 2/2 | 2/2 |

**Retrieval saja (27 kombinasi parameter, tanpa LLM)**

| Komponen | Latensi |
|---|---|
| Embedding query (`bge-m3`) | sekitar 300 sampai 500 ms |
| Pencarian dense | 0,26 sampai 0,39 ms |
| Pencarian hybrid (dense + BM25 + RRF) | 0,7 sampai 1,2 ms |
| Penolakan oleh penyaring relevansi | sekitar 0,4 detik (termasuk embedding query) |

Catatan metodologi, termasuk koreksi golden set dan keterbatasan pengukuran, ada di [docs/evaluation.md](docs/evaluation.md).

## 5. Struktur Proyek

```
.
├── app/
│   ├── api/                  FastAPI: main, deps, jobs (indexing latar belakang), schemas
│   │   └── routes/           chat, search, documents, index, health
│   ├── config.py             Pengaturan terpusat (pydantic-settings, membaca .env)
│   ├── loaders.py            Ekstraksi teks per format dan pemindaian direktori
│   ├── indexing.py           Chunking, embedding, sinkronisasi indeks inkremental
│   ├── store.py              Skema SQLite, FTS5, penyimpanan vektor
│   ├── retrieval.py          Pencarian hybrid, filter, deduplikasi, penyaring relevansi
│   ├── rag.py                Orkestrasi RAG, sitasi, streaming
│   ├── prompts.py            Template prompt sistem dan konteks
│   ├── ollama_client.py      Klien Ollama (embed, chat, penanganan error)
│   ├── privacy.py            Pembatasan koneksi ke host lokal
│   ├── logging_setup.py      Logging dengan penyamaran konten
│   └── cli_chat.py           Antarmuka baris perintah sederhana
├── data/
│   ├── sample/               Dokumen dummy (dibuat oleh skrip, ikut repositori)
│   ├── docs/                 Dokumen pengguna (diabaikan git)
│   └── index/                Basis data indeks (diabaikan git)
├── eval/                     Golden set, metrik, sweep, runner, laporan
├── frontend/                 Antarmuka web modular (Streamlit)
│   ├── client/               Klien HTTP REST API (base, system, doc, search, chat)
│   ├── components/           Komponen UI modular (header, sidebar, chat, sitasi, trace, log)
│   ├── state/                Manajemen sesi Streamlit dan riwayat percakapan
│   ├── utils/                Utilitas pemformat teks/angka dan parser SSE
│   ├── views/                Tampilan tab (chat, search, documents, system)
│   ├── app.py                Entrypoint antarmuka Streamlit
│   └── config.py             Konfigurasi klien frontend
├── scripts/                  make_sample_docs, check_env, test_llm, demo
├── tests/                    Pengujian unit dan integrasi (pytest)
├── docs/                     Dokumentasi rinci
├── Dockerfile                Multi-stage build (base, builder, runtime, backend, frontend)
├── docker-compose.yml        Orkestrasi kontainer (ollama, model-puller, backend, frontend)
├── docker-compose.host-ollama.yml  Orkestrasi mode host Ollama
├── .env.docker               Konfigurasi runtime kontainer
├── .env.example              Contoh konfigurasi lokal
├── CHANGELOG.md
└── pyproject.toml
```

## 6. Setup dan Menjalankan Proyek

### 6.1 Menjalankan dengan Docker (Metode Cepat / Zero Setup)

Metode ini disarankan agar pengguna tidak perlu memasang Python, uv, atau mengonfigurasi Ollama dan model secara manual.

#### Prasyarat Docker
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) terpasang dan dalam status berjalan.

#### Opsi A: Full Docker (Satu Perintah / Satu Klik)
Seluruh komponen (Ollama CPU, pengunduh model otomatis, backend FastAPI, dan frontend Streamlit) dijalankan di dalam jaringan kontainer privat:

- **Pengguna Windows**:
  Jalankan atau klik ganda berkas `scripts/docker-start.bat`.
- **Pengguna Linux / macOS**:
  ```bash
  chmod +x scripts/*.sh
  ./scripts/docker-start.sh
  ```
- **Terminal (Cross-Platform)**:
  ```bash
  docker compose up -d
  ```

Pada inisialisasi awal, kontainer `model-puller` akan otomatis mengunduh model `bge-m3` dan `qwen3:4b-instruct` ke volume persisten (`pda_ollama_models`). Setelah siap, akses:
- **Antarmuka Web Streamlit**: http://localhost:8501
- **Dokumentasi API Swagger**: http://localhost:8000/docs

Untuk menghentikan layanan:
- Windows: `scripts/docker-stop.bat`
- Terminal: `docker compose down`

#### Opsi B: Mode Host Ollama (Memanfaatkan Model Host)
Jika Anda sudah menginstal Ollama di komputer host dan tidak ingin mengunduh ulang model:
```bash
docker compose -f docker-compose.host-ollama.yml up -d
```

---

### 6.2 Setup Manual (Lokal Tanpa Docker)

#### 6.2.1 Prasyarat Manual

1. Python 3.11 atau lebih baru.
2. [uv](https://docs.astral.sh/uv/):
   ```powershell
   winget install astral-sh.uv
   ```
3. [Ollama](https://ollama.com/) terpasang dan berjalan di `http://127.0.0.1:11434`.
4. Ruang disk sekitar 4 GB untuk model dan RAM minimal 16 GB disarankan.

### 6.2.2 Konfigurasi Ollama untuk mode CPU

Langkah ini hanya diperlukan jika inferensi GPU gagal atau tidak diinginkan, seperti pada perangkat pengembangan. Atur variabel lingkungan satu kali, lalu restart Ollama:

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_VULKAN", "0", "User")
[Environment]::SetEnvironmentVariable("CUDA_VISIBLE_DEVICES", "-1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "2", "User")
```

Alternatif untuk satu sesi terminal:

```powershell
$env:OLLAMA_VULKAN = "0"
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "2"
ollama serve
```

### 6.2.3 Instalasi

```powershell
uv sync
Copy-Item .env.example .env
ollama pull bge-m3
ollama pull qwen3:4b-instruct
```

Model pembanding (opsional): `ollama pull qwen2.5:1.5b`.

### 6.2.4 Menyiapkan dokumen

Dokumen dummy:

```powershell
uv run python scripts/make_sample_docs.py
```

Perintah ini membuat enam berkas di `data/sample/`. Untuk dokumen sendiri, letakkan berkas di `data/docs/` (dapat berupa subfolder) atau unggah lewat API.

### 6.2.5 Membangun indeks

Indeks dapat dibangun lewat API (`POST /api/v1/index/update`) setelah server berjalan, atau saat dokumen diunggah. Status dipantau melalui `GET /api/v1/index/status`.

### 6.2.6 Menjalankan API

```powershell
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Gunakan satu worker karena status indexing dan antrean chat disimpan di memori proses. Jika port 8000 sudah digunakan oleh aplikasi lain di sistem Anda, gunakan port alternatif (misal `--port 8001`), dan set variabel `API_PORT=8001` atau `PDA_API_URL=http://127.0.0.1:8001/api/v1` saat menjalankan Streamlit.

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

### 6.2.7 Memeriksa lingkungan

```powershell
uv run python scripts/check_env.py
uv run python scripts/check_env.py --num-thread 4 8
uv run python scripts/check_env.py --models qwen3:4b-instruct qwen2.5:1.5b
```

Skrip ini memeriksa ketersediaan model serta mengukur kecepatan prefill dan generasi.

### 6.2.8 Menjalankan Antarmuka Web (Streamlit)

Setelah server API berjalan (langkah 6.6), buka terminal terpisah dan jalankan:

```powershell
uv run streamlit run frontend/app.py --server.port 8501 --server.address 127.0.0.1
```

Akses antarmuka grafis di peramban: `http://127.0.0.1:8501`. Antarmuka ini menyediakan:
- Tab **Chat RAG**: Percakapan dokumen (mode streaming atau non-streaming), kartu sitasi interaktif per chunk, visualisasi 8 tahap workflow trace, ringkasan latensi, dan reset chat.
- Tab **Retrieval Lab**: Pengujian pencarian komparatif (`hybrid`, `dense`, `bm25`) tanpa memanggil LLM beserta rincian skor.
- Tab **Documents**: Pengunggahan berkas multi-format dengan progress bar sinkronisasi, penampil daftar dokumen terindeks, inspeksi chunk, dan aksi hapus dokumen.
- Tab **System**: Status kesehatan backend & model Ollama, serta penampil log konsol real-time (`app.log`) dengan filter level.

## 7. Penggunaan API

Semua endpoint berada di bawah prefiks `/api/v1`.

| Method | Path | Fungsi |
|---|---|---|
| GET | `/health` | Status Ollama, model, jumlah dokumen, versi indeks |
| GET | `/system/logs` | Mengambil baris log server terbaru dengan filter level |
| POST | `/chat` | Tanya-jawab, respons JSON |
| POST | `/chat/stream` | Tanya-jawab, respons streaming (SSE) |
| POST | `/search` | Retrieval tanpa LLM (`hybrid`, `dense`, `bm25`) |
| GET | `/documents` | Daftar dokumen terindeks |
| GET | `/documents/{doc_id}` | Detail satu dokumen |
| POST | `/documents` | Unggah dokumen dan jadwalkan indexing |
| DELETE | `/documents/{doc_id}` | Hapus dokumen |
| GET | `/chunks/{chunk_id}` | Isi lengkap satu chunk |
| POST | `/index/update` | Sinkronisasi indeks di latar belakang |
| GET | `/index/status` | Progres sinkronisasi |

Contoh permintaan:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/chat" `
  -H "Content-Type: application/json" `
  -d '{\"question\": \"Berapa biaya sewa rumah dan durasinya?\", \"top_k\": 3}'
```

Streaming:

```powershell
curl.exe -N -X POST "http://127.0.0.1:8000/api/v1/chat/stream" `
  -H "Content-Type: application/json" `
  -d '{\"question\": \"Sebutkan rincian suku cadang servis 20.000 km mobil HR-V\"}'
```

Jika `API_KEY` diisi pada `.env`, sertakan header `X-API-Key`. Di Swagger UI, gunakan tombol **Authorize**.

Skema request dan response lengkap tersedia di Swagger UI dan diringkas pada [docs/api.md](docs/api.md).

## 8. Data yang Digunakan

Seluruh data pada repositori adalah **dummy** dan fiktif.

| Berkas dummy | Isi |
|---|---|
| `data/sample/rumah/kontrak-sewa.docx` | Perjanjian sewa rumah |
| `data/sample/arsip/polis-kesehatan.pdf` | Polis asuransi kesehatan (salinan kembar di `asuransi/`, untuk menguji deduplikasi) |
| `data/sample/keuangan/anggaran-rumah-tangga.xlsx` | Anggaran dan tabungan, beberapa sheet |
| `data/sample/kendaraan/catatan-servis.md` | Riwayat servis kendaraan |
| `data/sample/unduhan/artikel-tips.txt` | Artikel tips keuangan |

Pembuatan berkas dilakukan oleh `scripts/make_sample_docs.py`. Nama, alamat, nominal, dan kode pada berkas tersebut bukan data nyata.

Dokumen pribadi pengguna disimpan di `data/docs/`, sedangkan indeks di `data/index/`. Keduanya, bersama `.env`, `eval/reports/`, dan `eval/*.private.*`, dikecualikan dari git melalui `.gitignore`.

## 9. Pengujian dan Evaluasi

Pengujian otomatis:

```powershell
uv run pytest
```

Saat ini terdapat 68 pengujian. `pytest-socket` memblokir koneksi keluar selama pengujian; hanya loopback yang diizinkan.

Evaluasi kualitas:

```powershell
# Sweep parameter retrieval (tanpa LLM)
uv run python -m eval.sweep --golden eval/golden.sample.jsonl

# Evaluasi end-to-end untuk satu atau lebih model
uv run python -m eval.run --golden eval/golden.sample.jsonl --models qwen3:4b-instruct qwen2.5:1.5b --k 4 --show-failures
```

Laporan ditulis ke `eval/reports/` dalam format Markdown dan CSV. Panduan membuat golden set untuk dokumen pribadi ada di [eval/README.md](eval/README.md).

## 10. Keterbatasan

- Golden set hanya berisi 20 pertanyaan dengan 6 dokumen dummy. Hasil evaluasi menunjukkan perilaku pada data tersebut dan tidak dapat digeneralisasi ke koleksi dokumen yang lebih besar atau lebih beragam.
- Pertanyaan evaluasi dibuat oleh pengembang sistem, sehingga hasil retrieval 100% pada dataset ini tidak berarti retrieval akan sama pada data lain.
- Nilai TTFT pada laporan evaluasi tercatat 0 ms karena belum diambil dari metrik Ollama; hanya kecepatan generasi dan durasi total yang dapat diandalkan.
- Penilaian jawaban memakai pencocokan kata kunci, bukan penilaian semantik.
- OCR belum tersedia; PDF hasil pemindaian hanya ditandai.
- Memori percakapan disimpan di sisi klien; server tidak menyimpan sesi.
- Satu worker dan satu permintaan chat bersamaan (`MAX_CONCURRENT_CHAT=1`).
- Nilai default ambang penyaring relevansi (`MIN_DENSE_SCORE=0.35`, `MIN_BM25_SCORE=0.0`) berbeda dari nilai yang menghasilkan akurasi penolakan tertinggi pada sweep (0,45 dan 1,0). Lihat [docs/evaluation.md](docs/evaluation.md).
- Pengujian hanya dilakukan di Windows 11 dengan satu konfigurasi perangkat.

## 11. Rekomendasi Upgrade

Ringkasan; rincian dan alasan ada di [docs/upgrade-recommendations.md](docs/upgrade-recommendations.md).

| Prioritas | Usulan |
|---|---|
| Selesai | Antarmuka web modular di atas API (diimplementasikan di v0.2.0 via Streamlit) |
| Tinggi | Perluas golden set dan gunakan dokumen nyata melalui `eval/golden.private.jsonl` |
| Tinggi | Tinjau nilai default ambang relevansi berdasarkan hasil sweep |
| Tinggi | Catat TTFT dari metrik prefill Ollama pada runner evaluasi |
| Sedang | Tambahkan OCR untuk PDF pindaian |
| Sedang | Uji model LLM lain dan model embedding alternatif pada koleksi yang lebih besar |
| Sedang | Aktifkan query rewrite secara selektif untuk pertanyaan lanjutan |
| Sedang | Tambahkan reranker pada hasil retrieval |
| Rendah | Penyimpanan sesi percakapan di sisi server |
| Rendah | Dukungan GPU atau perangkat dengan VRAM lebih besar untuk model yang lebih besar |

## 12. Dokumentasi Lanjutan

| Dokumen | Isi |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Arsitektur, alur data, skema penyimpanan, keputusan desain |
| [docs/configuration.md](docs/configuration.md) | Seluruh parameter `.env` |
| [docs/api.md](docs/api.md) | Ringkasan endpoint dan format respons |
| [docs/evaluation.md](docs/evaluation.md) | Metodologi dan hasil evaluasi |
| [docs/upgrade-recommendations.md](docs/upgrade-recommendations.md) | Rekomendasi pengembangan lanjutan |
| [eval/README.md](eval/README.md) | Panduan menjalankan evaluasi |
| [CHANGELOG.md](CHANGELOG.md) | Riwayat perubahan dan versi |
