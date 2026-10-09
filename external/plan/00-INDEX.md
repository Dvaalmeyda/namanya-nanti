# INDEKS - Rencana pengembangan asisten AI dokumen pribadi (lokal, offline)

Kumpulan prompt untuk AI coding agent (di IDE), satu fase per file. Konteks bersama ada di `00-KONTEKS.md` sehingga tidak perlu disalin ke setiap fase.

## Cara pakai
1. Satu fase = satu sesi agent. Di awal sesi, minta agent membaca `00-KONTEKS.md` lalu file fase yang dikerjakan (atau tempel keduanya).
2. Jangan gabungkan fase. Setelah agent melapor, cek sendiri "Kriteria selesai", commit, baru lanjut.
3. Bila hasil fase belum memuaskan, perbaiki di fase yang sama; jangan menambal di fase berikutnya.
4. Dokumen asli tidak pernah masuk repo atau sesi agent. Tes hanya memakai dokumen dummy.

## Daftar fase
| # | File | Hasil utama | Bergantung pada |
|---|------|-------------|-----------------|
| 0 | fase-0-setup-proyek.md | `pyproject.toml` (uv), config, guard offline, klien Ollama, dokumen dummy, `check_env` (prefill, generate, embed, CPU vs GPU) | - |
| 1 | fase-1-loader-dokumen.md | `app/loaders.py`: PDF/DOCX/XLSX/MD/TXT jadi `Block` + metadata (folder, tipe, tanggal, lokasi) | 0 |
| 2 | fase-2-indexing.md | `app/store.py` + `app/indexing.py`: chunking, embedding, satu SQLite (FTS5 + vektor), incremental per path | 1 |
| 3 | fase-3-retrieval-rag.md | Hybrid search (RRF), gerbang penolakan gabungan, sitasi bernomor, riwayat opsional, CLI chat | 2 |
| 4 | fase-4-api.md | FastAPI + Swagger: chat (JSON dan SSE), search, dokumen (upload/hapus), indexing background, hardening ringan | 3 |
| 5 | fase-5-evaluasi.md | Golden set, metrik kualitas + latensi, sweep dua tahap (retrieval lalu LLM), pemilihan konfigurasi final | 4 |
| 6 | fase-6-frontend-streamlit.md | Frontend Streamlit modular: chat RAG streaming, visualisasi alur kerja/trace log, manajemen dokumen | 4 |

API dibangun sebelum evaluasi agar sistem bisa dicoba lewat Swagger sedini mungkin. Evaluasi memakai modul yang sama (bukan lewat HTTP), jadi urutan ini tidak mengubah hasil.

## Keputusan teknis
| Komponen | Pilihan | Alasan singkat |
|---|---|---|
| LLM | Ollama, baseline `qwen3:4b-instruct` (`think=False`) | Muat di RAM 16 GB, non-thinking lebih cepat. Kandidat lain (`qwen3.5:4b`, `gemma4:e4b`, `qwen3.5:2b`, `gemma4:e2b`) dibandingkan di Fase 5 |
| Embedding | Ollama, baseline `bge-m3` | Multibahasa, kuat untuk bahasa Indonesia. Dibandingkan dengan `qwen3-embedding:0.6b`, `embeddinggemma`, `embeddinggemma-2` di Fase 5 |
| Penyimpanan | Satu SQLite (WAL): metadata + teks + FTS5 + embedding BLOB | Satu transaksi atomik, tanpa lock antarproses, tanpa dependensi tambahan |
| Dense search | numpy brute-force di memori | Qdrant mode lokal juga brute-force; untuk skala pribadi (puluhan ribu chunk) kueri di bawah 50 ms |
| BM25 | SQLite FTS5 (`unicode61 remove_diacritics 2`), stemmer Sastrawi opsional | Bawaan Python, persisten |
| API | FastAPI, `/api/v1`, Swagger | `/chat` mengembalikan JSON utuh agar bisa diuji di Swagger; SSE di endpoint terpisah |
| Orkestrasi | Modul sendiri, tanpa framework | Alur terlihat jelas dan mudah diukur |

## Aturan emas
- Tidak ada panggilan ke layanan eksternal, telemetry, atau tracing cloud saat runtime.
- Log tidak berisi isi dokumen atau isi pertanyaan secara default.
- Setiap fitur yang menambah panggilan LLM (query rewriting, reranker, dsb.) default mati dan harus dibuktikan bermanfaat di Fase 5.
- Konfigurasi final (model, TOP_K, ukuran chunk, ambang penolakan) adalah keputusan berbasis data dari Fase 5, bukan tebakan. Target kualitas dan latensi ditetapkan oleh pengguna.

## Struktur target repo (di root workspace)
```
app/
  config.py  logging_setup.py  privacy.py  ollama_client.py
  loaders.py  store.py  indexing.py  retrieval.py  rag.py  prompts.py  cli_chat.py
  api/        main.py  deps.py  schemas.py  jobs.py  routes/
eval/         golden.sample.jsonl  run.py  sweep.py  README.md  reports/
scripts/      check_env.py  make_sample_docs.py
data/         sample/  docs/  index/
tests/
pyproject.toml  .env.example  README.md
```
`data/docs/`, `data/index/`, `eval/reports/`, `eval/*.private.*`, dan `.env` di-gitignore.

## Yang sengaja tidak termasuk
- **Frontend/UI**: di luar lingkup; Swagger adalah antarmuka uji. Bila kelak perlu, endpoint kompatibel OpenAI bisa ditambahkan agar Open WebUI dapat dipakai.
- **ACL per role, multi-user, audit log, threat model penuh**: tidak relevan untuk satu pengguna. Hardening yang tetap relevan (guard offline, log bersih, uji prompt injection, proteksi upload) dilebur ke Fase 4 dan 5.
- **Agentic RAG**: setiap langkah agent memakan 15-40 detik di CPU laptop, bertentangan dengan target kecepatan.

## Ide lanjutan (setelah Fase 5, bila data mendukung)
- OCR lokal untuk PDF hasil scan (Tesseract atau model vision lokal), opt-in.
- Reranker (butuh PyTorch/ONNX) bila evaluasi menunjukkan retrieval sebagai hambatan.
- Pindah ke Qdrant server atau `sqlite-vec` bila jumlah chunk mencapai ratusan ribu.
- Saat pindah ke mesin GPU: ubah `LLM_MODEL`, `OLLAMA_HOST` (dengan `ALLOW_REMOTE` terkontrol), lalu jalankan ulang Fase 5 untuk kalibrasi.
