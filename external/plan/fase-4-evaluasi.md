# FASE 4 - Evaluasi dan kalibrasi

> Prasyarat: Fase 3 selesai.

## KONTEKS PROYEK (selalu tempel di awal sesi)
- Proyek: asisten AI tanya-jawab atas dokumen internal perusahaan yang SANGAT RAHASIA. Semuanya berjalan lokal.
- Larangan mutlak: tidak ada panggilan ke layanan eksternal (API LLM cloud, telemetry, tracing cloud, CDN, font atau skrip eksternal). Hanya localhost.
- Lingkungan awal: laptop Windows 11 (PowerShell), CPU-only (i7-1165G7, RAM 16 GB; GPU MX450 2 GB tidak dipakai). Kelak dipindah ke server dengan GPU, jadi semua pengaturan lewat config/.env; tidak ada path atau nama model yang di-hardcode.
- Stack terkunci: Python 3.11+ dengan uv, Ollama (LLM `qwen3:4b-instruct`, embedding `bge-m3`), Qdrant mode lokal (tanpa server), SQLite FTS5 untuk BM25, FastAPI. Dokumen berbahasa Indonesia (sebagian Inggris).
- Data: dokumen asli TIDAK boleh masuk repo. Pengembangan dan tes hanya memakai dokumen dummy di `data/sample/`. Jangan pernah mencatat isi dokumen atau isi pertanyaan di log.
- Cara kerja: tulis rencana singkat dulu, lalu implementasi, tes, dan jalankan. Jangan menambah dependensi tanpa alasan tertulis. Jelaskan keputusan penting dalam 1-2 kalimat. Kerjakan HANYA fase ini; berhenti dan lapor setelah selesai.

## TUGAS
Bangun harness evaluasi di `eval/`.

1. Golden set `eval/golden.sample.jsonl` (untuk dokumen dummy) dengan field: `id`, `question`, `type` (faktual | tabel | multi-dokumen | tidak-ada-jawaban | injection), `expected_answer` (singkat), `must_include` (list kata atau angka kunci), `must_not_include` (list), `gold_sources` (list `{file, page}`), `role`. Buat 15 contoh dari dokumen sample, termasuk 3 tidak-ada-jawaban dan 2 injection. Set nyata disimpan di `eval/golden.private.jsonl` (gitignored).
2. Metrik retrieval: hit@k, recall@k, MRR terhadap `gold_sources`.
3. Metrik jawaban: cakupan `must_include`, pelanggaran `must_not_include`, akurasi penolakan (tipe tidak-ada-jawaban harus `refused`), ketepatan sitasi (file yang disitasi termasuk `gold_sources`), serta latensi (retrieval, TTFT, total, token/detik; rata-rata dan p95). LLM-as-judge opsional dan nonaktif secara default (model kecil lokal bukan juri yang andal).
4. Runner: `python -m eval.run --golden eval/golden.sample.jsonl --models qwen3:4b-instruct gemma3:4b qwen3:8b --k 4 --mode hybrid|dense|bm25`. Keluaran: tabel Markdown dan CSV di `eval/reports/` (gitignored). Opsi `--show-failures` menampilkan 5 kasus terburuk (dengan peringatan karena menampilkan isi chunk).
5. `python -m eval.sweep` sederhana untuk membandingkan konfigurasi: mode retrieval, `CHUNK_SIZE`, `TOP_K`, `MIN_DENSE_SCORE` (grid kecil).
6. `eval/README.md`: cara menulis 30-50 pertanyaan nyata (campuran tipe) dan usulan target awal yang bisa diubah (misalnya hit@4 >= 0.85, akurasi penolakan >= 0.9, 0 kebocoran ACL). Tegaskan bahwa target adalah keputusan produk.

## BATASAN
- Jangan commit apa pun yang berisi pertanyaan atau jawaban nyata.
- Jangan menambah dependensi evaluasi berat; pustaka standar dan pandas cukup.

## KRITERIA SELESAI
- Runner berjalan pada sample set untuk minimal dua model dan menghasilkan tabel perbandingan.
- Laporkan saran nilai `MIN_DENSE_SCORE` dari data sample, dengan catatan bahwa harus dikalibrasi ulang pada dokumen nyata.
