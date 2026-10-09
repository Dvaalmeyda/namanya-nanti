# Changelog

Seluruh perubahan dan pembaruan versi pada proyek Personal Document Assistant didokumentasikan dalam berkas ini. Format pencatatan mengikuti prinsip semantic versioning.

---

## [0.2.0] - 2026-10-09

Pembaruan besar yang menambahkan antarmuka web pengguna modular berbasis Streamlit dan endpoint diagnostik log sistem.

### Ditambahkan

#### Fase 6: Frontend Aplikasi (Streamlit Modular)
- Antarmuka web pengguna interaktif berbasis Streamlit di `frontend/app.py` yang berkomunikasi 100% melalui REST API tanpa akses langsung ke basis data atau Ollama.
- Arsitektur antarmuka modular dengan pembatasan ketat di bawah 150-200 baris kode per berkas:
  - `frontend/config.py`: Konfigurasi terpusat untuk alamat API, timeout, dan interval polling.
  - `frontend/utils/formatters.py`: Utilitas pemformat angka, waktu latensi, ukuran berkas, kecepatan token, dan badge status visual.
  - `frontend/utils/sse_parser.py`: Parser aliran Server-Sent Events (SSE) untuk streaming respons percakapan.
  - `frontend/client/`: Klien HTTP terstruktur (`base.py`, `system_client.py`, `document_client.py`, `search_client.py`, `chat_client.py`) dengan penanganan galat terstandarisasi.
  - `frontend/state/`: Pengelolaan sesi reaktif (`session.py`, `chat_state.py`) untuk riwayat percakapan dan jejak alur kerja per giliran.
  - `frontend/components/`: Komponen visual modular (`header.py`, `sidebar.py`, `chat_bubble.py`, `citation_viewer.py`, `workflow_trace.py`, `metrics_display.py`, `file_uploader.py`, `system_logs.py`).
  - `frontend/views/`: 4 tampilan utama berbasis tab (`chat_view.py`, `search_view.py`, `documents_view.py`, `system_view.py`).
- Fitur Transparansi Alur Kerja (Workflow Trace 8 Tahap): visualisasi langkah inferensi RAG per giliran chat (penerimaan pertanyaan, pemfilteran metadata, embedding query, hybrid retrieval, relevance gate, perakitan prompt, generasi LLM, dan pemetaan sitasi).
- Tampilan Chat RAG: Mendukung pilihan mode streaming SSE dan non-streaming JSON, kartu sitasi interaktif per rujukan chunk dokumen, ringkasan latensi, dan pembersih riwayat sesi.
- Tampilan Laboratorium Retrieval: Fasilitas pengujian komparasi mode retrieval (`hybrid`, `dense`, `bm25`) tanpa pemanggilan LLM, visualisasi skor Reciprocal Rank Fusion, dan cuplikan teks chunk.
- Tampilan Manajemen Dokumen: Daftar dokumen terindeks, inspeksi konten lengkap chunk, unggah berkas multi-format dengan pemantau progres indexing berkala, dan aksi penghapusan dokumen.
- Tampilan Status Sistem: Pemantauan kesehatan server backend, verifikasi model Ollama yang termuat, dan penampil log server real-time (`app.log`) dengan filter level dan penyamaran konten otomatis (`[REDACTED]`).
- Endpoint REST API baru pada backend: `GET /api/v1/system/logs` di `app/api/routes/health.py` dengan skema `SystemLogsResponse` untuk membaca baris log server terbaru secara aman.
- Rangkaian pengujian unit baru di `tests/test_frontend.py` untuk validasi formatters, parser SSE, batasan baris kode per berkas, dan kepatuhan bebas emotikon, meningkatkan total pengujian menjadi 68 tes passing.

---

## [0.1.0] - 2026-10-08

Versi awal sistem yang mengimplementasikan seluruh fungsi dasar tanya-jawab dokumen pribadi berbasis Retrieval-Augmented Generation (RAG) secara lokal.

### Ditambahkan

#### Fase 0: Fondasi Lingkungan, Privasi, dan Klien Ollama
- Manajemen dependensi dan virtual environment menggunakan `uv`.
- Modul konfigurasi terpusat `app/config.py` berbasis Pydantic Settings yang memuat parameter dari `.env`.
- Modul klien Ollama `app/ollama_client.py` yang menangani pemanggilan embedding (`embed`) dan chat (`chat`) dengan fallback timeout, verifikasi ketersediaan model, serta penanganan error koneksi.
- Modul pembatas privasi `app/privacy.py` untuk menolak alamat host di luar loopback (`127.0.0.1`, `localhost`, `::1`) kecuali jika `ALLOW_REMOTE=true`.
- Modul logging terproteksi `app/logging_setup.py` dengan filter sensor untuk mencegah pencatatan isi dokumen atau teks kueri pengguna ke log ketika `LOG_CONTENT=false`.
- Skrip diagnostik lingkungan `scripts/check_env.py` untuk memeriksa ketersediaan model, konfigurasi thread CPU, serta latensi inferensi.
- Konfigurasi pengujian `pytest` dengan proteksi soket jaringan (`pytest-socket`) untuk memastikan pengujian unit tidak melakukan koneksi keluar.

#### Fase 1: Ekstraksi Dokumen Multi-Format (Data Loaders)
- Modul loader `app/loaders.py` yang mendukung 5 format dokumen:
  - PDF: Ekstraksi teks berbasis halaman menggunakan PyMuPDF (`fitz`), deteksi halaman hasil pemindaian (scanned PDF) yang memerlukan OCR.
  - DOCX: Ekstraksi paragraf dan tabel berbasis struktur menggunakan `python-docx`.
  - XLSX: Ekstraksi lembar kerja berbasis grup baris menggunakan `openpyxl`, dikonversi ke format tabel Markdown.
  - Markdown dan TXT: Ekstraksi teks langsung berbasis baris dan heading.
- Pelacakan metadata dokumen: hash konten SHA-256, ukuran berkas, waktu modifikasi, serta penomoran lokasi asal (halaman, bab, baris sheet).
- Skrip pembantu `scripts/make_sample_docs.py` untuk menghasilkan 6 berkas dokumen dummy di `data/sample/`.

#### Fase 2: Pengindeksan, Chunking, dan Penyimpanan Vektor
- Skema basis data SQLite terpadu di `app/store.py` (`data/index/index.db`) dengan tabel:
  - `documents`: Menyimpan metadata berkas, hash konten, dan status pemrosesan.
  - `chunks`: Menyimpan potongan teks, penanda lokasi, dan ID dokumen induk.
  - `chunks_fts`: Indeks FTS5 (Full-Text Search) untuk pencarian kata kunci leksikal berbasis BM25.
  - `settings`: Menyimpan versi indeks dan metadata sinkronisasi.
- Penyimpanan vektor dense berbasis file array biner NumPy (`vectors.npy` dan `chunk_ids.npy`).
- Modul chunking rekursif di `app/indexing.py` dengan parameter ukuran potongan (`CHUNK_SIZE`) dan tumpang-tindih (`CHUNK_OVERLAP`).
- Mekanisme sinkronisasi inkremental: berkas yang tidak berubah dilewati berdasarkan perbandingan SHA-256.
- Penanganan dokumen kembar (konten identik di lokasi berbeda): penggunaan ulang embedding tanpa duplikasi vektor komputasi, dengan metadata `also_in`.
- Transaksi atomik dan penguncian proses (*indexing lock*) untuk mencegah konkurensi indexing yang bertabrakan.

#### Fase 3: Mesin Retrieval Hybrid dan Orkestrasi RAG
- Modul retrieval `app/retrieval.py` yang mendukung 3 mode pencarian:
  - `dense`: Pencarian kemiripan kosinus (cosine similarity) berbasis vektor representasi `bge-m3`.
  - `bm25`: Pencarian kata kunci berbasis FTS5 SQLite.
  - `hybrid`: Penggabungan peringkat dense dan BM25 menggunakan metode Reciprocal Rank Fusion (RRF, k=60).
- Penyaringan metadata berdasarkan folder, tipe berkas, atau daftar ID dokumen.
- Gerbang penolakan relevansi (*relevance gate*): mendeteksi kueri di luar domain dokumen menggunakan ambang batas skor kemiripan (`MIN_DENSE_SCORE` dan `MIN_BM25_SCORE`), menolak pertanyaan yang tidak relevan tanpa memanggil LLM.
- Modul orkestrasi RAG `app/rag.py`:
  - Penyusunan prompt terstruktur dengan pembatas teks dokumen guna mencegah eksploitasi prompt injection.
  - Integrasi riwayat percakapan pengguna untuk pertanyaan rujukan/lanjutan.
  - Pascapemrosesan sitasi: ekstraksi penanda `[1]`, `[2]` dari jawaban dan pemetaan balik ke metadata sumber.
  - Mode eksekusi sinkron (`answer`) dan mode streaming generator (`answer_stream`).

#### Fase 4: Antarmuka REST API dan Manajemen Pekerjaan Latar Belakang
- Server REST API berbasis FastAPI di `app/api/main.py` yang berjalan di loopback lokal (`127.0.0.1:8000`).
- Endpoint interaktif terdokumentasi via Swagger UI (`/docs`) dan ReDoc (`/redoc`).
- Endpoint utama:
  - `GET /api/v1/health`: Memeriksa kesehatan sistem, status Ollama, model yang termuat, dan status indeks.
  - `POST /api/v1/chat`: Antarmuka tanya-jawab RAG dengan keluaran JSON terstruktur.
  - `POST /api/v1/chat/stream`: Antarmuka tanya-jawab streaming berbasis Server-Sent Events (SSE).
  - `POST /api/v1/search`: Pencarian potongan dokumen murni tanpa inferensi LLM.
  - `GET /api/v1/documents`: Daftar dokumen yang tersimpan dalam indeks.
  - `GET /api/v1/documents/{doc_id}`: Detail metadata dan daftar chunk satu dokumen.
  - `POST /api/v1/documents`: Unggah berkas dokumen dengan validasi tipe, ukuran, dan sanitasi nama berkas.
  - `DELETE /api/v1/documents/{doc_id}`: Menghapus dokumen beserta potongan dan vektor terkait dari indeks.
  - `GET /api/v1/chunks/{chunk_id}`: Mengambil teks lengkap satu potongan dokumen.
  - `POST /api/v1/index/update`: Menjadwalkan sinkronisasi indeks di latar belakang.
  - `GET /api/v1/index/status`: Memantau progres sinkronisasi indeks.
- Manajer pekerjaan latar belakang `app/api/jobs.py` untuk mengelola proses indexing asinkron.
- Skema validasi permintaan dan tanggapan Pydantic di `app/api/schemas.py`.
- Pembatasan konkurensi chat (`MAX_CONCURRENT_CHAT=1`) untuk menjaga stabilitas RAM dan CPU.
- Mekanisme autentikasi opsional berbasis header `X-API-Key`.

#### Fase 5: Pengujian Kuantitatif, Kalibrasi Parameter, dan Evaluasi
- Dataset evaluasi acuan `eval/golden.sample.jsonl` yang memuat 20 pertanyaan beranotasi lengkap mencakup 5 kategori kueri (faktual/tabel/kode, multi-dokumen, lanjutan, tidak ada jawaban / OOD, dan prompt injection).
- Modul kalkulasi metrik kuantitatif `eval/metrics.py` (`Hit@K`, `Recall@K`, `MRR`, `Keyword Coverage`, `Refusal Accuracy`, `Injection Defense`, `Citation Precision`).
- Skrip sweep parameter retrieval `eval/sweep.py` yang menguji 27 kombinasi konfigurasi retrieval tanpa pemanggilan LLM menggunakan cache vektor kueri.
- Runner evaluasi end-to-end `eval/run.py` untuk mengukur kualitas jawaban, profil latensi per tahap, dan perbandingan performa lintas model LLM.
- Berkas panduan evaluasi privat `eval/README.md`.
- Rangkaian pengujian unit otomatis di `tests/` yang mencakup 60 tes passing secara keseluruhan.
