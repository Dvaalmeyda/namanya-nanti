# FASE 5 - API dan antarmuka

> Prasyarat: Fase 3 selesai (Fase 4 sebaiknya sudah).

## KONTEKS PROYEK (selalu tempel di awal sesi)
- Proyek: asisten AI tanya-jawab atas dokumen internal perusahaan yang SANGAT RAHASIA. Semuanya berjalan lokal.
- Larangan mutlak: tidak ada panggilan ke layanan eksternal (API LLM cloud, telemetry, tracing cloud, CDN, font atau skrip eksternal). Hanya localhost.
- Lingkungan awal: laptop Windows 11 (PowerShell), CPU-only (i7-1165G7, RAM 16 GB; GPU MX450 2 GB tidak dipakai). Kelak dipindah ke server dengan GPU, jadi semua pengaturan lewat config/.env; tidak ada path atau nama model yang di-hardcode.
- Stack terkunci: Python 3.11+ dengan uv, Ollama (LLM `qwen3:4b-instruct`, embedding `bge-m3`), Qdrant mode lokal (tanpa server), SQLite FTS5 untuk BM25, FastAPI. Dokumen berbahasa Indonesia (sebagian Inggris).
- Data: dokumen asli TIDAK boleh masuk repo. Pengembangan dan tes hanya memakai dokumen dummy di `data/sample/`. Jangan pernah mencatat isi dokumen atau isi pertanyaan di log.
- Cara kerja: tulis rencana singkat dulu, lalu implementasi, tes, dan jalankan. Jangan menambah dependensi tanpa alasan tertulis. Jelaskan keputusan penting dalam 1-2 kalimat. Kerjakan HANYA fase ini; berhenti dan lapor setelah selesai.

## TUGAS
Bangun API dan UI minimal di atas `RagResult` dari Fase 3.

1. `app/api.py` (FastAPI), bind ke 127.0.0.1 secara default, CORS tertutup:
   - `GET /health`
   - `POST /chat` (streaming SSE: token, lalu event `sources`, lalu `done` dengan timing)
   - `GET /documents` (hanya dokumen yang boleh diakses role pengguna)
   - `GET /chunks/{chunk_id}` (tampilkan chunk yang disitasi bila diizinkan; 404 jika terlarang, bukan 403)
   - `POST /admin/index/update` (khusus admin; jalankan di dalam proses API dengan client Qdrant yang sama, serial lewat lock, karena Qdrant mode lokal hanya dapat dibuka satu proses; CLI indexing tidak boleh berjalan bersamaan)
2. Autentikasi prototipe: API key per pengguna di `config/users.yaml` (simpan hash, bukan teks asli) yang dipetakan ke role. Sediakan `scripts/add_user.py`.
3. UI: satu halaman statis `app/static/index.html` dengan HTML, CSS, dan JS biasa. TANPA CDN, font, atau skrip eksternal. Tampilkan jawaban streaming, kartu sumber (file, halaman, klik untuk melihat chunk), status "tidak ditemukan", dan tombol salin. Riwayat chat hanya di memori browser.
4. Opsional (stretch): endpoint kompatibel OpenAI `/v1/chat/completions` agar Open WebUI dapat dipakai sebagai antarmuka.

## BATASAN
- Jangan menyimpan percakapan di server.
- Jangan membuka port ke luar localhost.

## KRITERIA SELESAI
- Tes `TestClient`: streaming berjalan, role A tidak dapat melihat dokumen atau chunk milik role B (404), admin dapat memicu update.
- Cek manual lewat browser; tuliskan langkah menjalankan di PowerShell.
