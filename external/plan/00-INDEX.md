# INDEKS - Prompt pengembangan asisten AI untuk dokumen rahasia (lokal)

Kumpulan prompt untuk AI coding agent (misalnya di IDE), satu fase per file. Setiap file sudah memuat konteks proyek, jadi bisa ditempel langsung ke sesi baru.

## Cara pakai
1. Satu fase = satu sesi agent. Tempel seluruh isi file fase.
2. Jangan gabungkan fase. Setelah agent melapor, cek sendiri "Kriteria selesai", commit, baru lanjut.
3. Bila hasil fase belum memuaskan, perbaiki di fase yang sama; jangan menambal di fase berikutnya.
4. Dokumen asli tidak pernah masuk repo atau sesi agent. Tes hanya memakai dokumen dummy.

## Daftar fase
| # | File | Hasil utama | Bergantung pada |
|---|------|-------------|-----------------|
| 0 | fase-0-setup-proyek.md | Kerangka repo, config, guard offline, dokumen dummy, check_env | - |
| 1 | fase-1-loader-dokumen.md | `app/loaders.py`: PDF/DOCX/XLSX/MD jadi `Block` + metadata ACL | 0 |
| 2 | fase-2-indexing.md | `app/indexing.py` (satu file): chunking, embedding, SQLite FTS5 + Qdrant, incremental | 1 |
| 3 | fase-3-retrieval-rag.md | Hybrid search (RRF), jawaban bersitasi, penolakan, CLI chat | 2 |
| 4 | fase-4-evaluasi.md | Golden set, metrik, perbandingan model dan konfigurasi | 3 |
| 5 | fase-5-api-ui.md | FastAPI + UI statis tanpa CDN, API key per role | 3 (4 disarankan) |
| 6 | fase-6-keamanan-audit.md | Threat model, audit log, uji injection dan ACL | 5 |
| 7 | fase-7-agentic-opsional.md | Agentic RAG dengan LangGraph (opsional) | 4 dan 6 |

## Keputusan teknis yang dikunci
| Komponen | Pilihan | Alasan singkat |
|---|---|---|
| LLM | Ollama `qwen3:4b-instruct` | Muat di RAM 16 GB, mode non-thinking lebih cepat untuk RAG |
| Embedding | `bge-m3` (Ollama) | Multibahasa, cocok untuk dokumen Indonesia |
| Vector store | Qdrant mode lokal | Tanpa server; satu proses pada satu waktu |
| BM25 | SQLite FTS5 | Bawaan Python, persisten, mudah dihapus per dokumen |
| API | FastAPI | Streaming SSE, mudah dites |
| UI | HTML statis | Tanpa CDN agar tidak ada permintaan keluar |
| Orkestrasi | Modul sendiri (Fase 1-6), LangGraph (Fase 7) | Alur terlihat jelas dulu, framework belakangan |

## Aturan emas
- Tidak ada panggilan ke layanan eksternal, telemetry, atau tracing cloud.
- Log tidak pernah berisi isi dokumen atau isi pertanyaan.
- ACL diterapkan di dalam kueri retrieval, bukan setelah hasil didapat.
- Target kualitas (hit@k, akurasi penolakan, dsb.) adalah keputusan produk; tetapkan di Fase 4 berdasarkan pertanyaan nyata.

## Struktur target repo
```
doc-assistant/
  app/        loaders.py  indexing.py  retrieval.py  rag.py  prompts.py  api.py  static/  agent/
  eval/       golden.sample.jsonl  run.py  sweep.py  reports/
  scripts/    check_env.py  make_sample_docs.py  add_user.py
  config/     acl.yaml  users.yaml
  data/       sample/  index/  private/  audit/
  docs/       threat-model.md  security-checklist.md
  tests/
```

## Catatan
- Fase deployment ke server (Docker Compose, vLLM, SSO) belum termasuk; tambahkan setelah spesifikasi server jelas.
- Saat pindah ke server GPU, cukup ubah `LLM_MODEL`, `OLLAMA_HOST` (alamat internal, dengan `ALLOW_REMOTE` terkontrol), lalu jalankan ulang Fase 4 untuk kalibrasi.
