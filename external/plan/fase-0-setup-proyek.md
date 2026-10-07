# FASE 0 - Setup proyek dan lingkungan

> Prasyarat: Ollama terpasang, serta `ollama pull qwen3:4b-instruct` dan `ollama pull bge-m3` sudah dijalankan.

## KONTEKS PROYEK (selalu tempel di awal sesi)
- Proyek: asisten AI tanya-jawab atas dokumen internal perusahaan yang SANGAT RAHASIA. Semuanya berjalan lokal.
- Larangan mutlak: tidak ada panggilan ke layanan eksternal (API LLM cloud, telemetry, tracing cloud, CDN, font atau skrip eksternal). Hanya localhost.
- Lingkungan awal: laptop Windows 11 (PowerShell), CPU-only (i7-1165G7, RAM 16 GB; GPU MX450 2 GB tidak dipakai). Kelak dipindah ke server dengan GPU, jadi semua pengaturan lewat config/.env; tidak ada path atau nama model yang di-hardcode.
- Stack terkunci: Python 3.11+ dengan uv, Ollama (LLM `qwen3:4b-instruct`, embedding `bge-m3`), Qdrant mode lokal (tanpa server), SQLite FTS5 untuk BM25, FastAPI. Dokumen berbahasa Indonesia (sebagian Inggris).
- Data: dokumen asli TIDAK boleh masuk repo. Pengembangan dan tes hanya memakai dokumen dummy di `data/sample/`. Jangan pernah mencatat isi dokumen atau isi pertanyaan di log.
- Cara kerja: tulis rencana singkat dulu, lalu implementasi, tes, dan jalankan. Jangan menambah dependensi tanpa alasan tertulis. Jelaskan keputusan penting dalam 1-2 kalimat. Kerjakan HANYA fase ini; berhenti dan lapor setelah selesai.

## TUGAS
Siapkan kerangka proyek dan pastikan lingkungan lokal berfungsi.

1. Struktur repo `doc-assistant/`: `app/`, `eval/`, `scripts/`, `tests/`, `docs/`, `config/`, `data/sample/`, `data/index/` (gitignored), `data/private/` (gitignored). Pakai `pyproject.toml` dengan `uv`.
2. `app/config.py` (pydantic-settings): OLLAMA_HOST (default http://127.0.0.1:11434), LLM_MODEL, EMBED_MODEL, NUM_CTX (4096), TEMPERATURE (0.1), DATA_DIR, INDEX_DIR, TOP_K (4), MIN_DENSE_SCORE, ALLOW_REMOTE (default false). Sediakan `.env.example`.
3. `app/logging_setup.py`: logging terstruktur ke console dan file, dengan filter yang membuang field berisi teks dokumen atau pertanyaan.
4. `app/privacy.py`: `apply_offline_env()` yang mengatur ANONYMIZED_TELEMETRY=False, DO_NOT_TRACK=1, LANGCHAIN_TRACING_V2=false, dan HF_HUB_OFFLINE=1 (opsional lewat flag); serta `assert_local_only(url)` yang menolak host non-loopback kecuali ALLOW_REMOTE=true.
5. `scripts/check_env.py`: cek Ollama dapat dihubungi, model LLM dan embedding sudah di-pull (jika belum, cetak perintah `ollama pull ...`), ukur kecepatan generate (token/detik dari eval_count dan eval_duration) dan waktu embed 16 kalimat. Cetak hasil dalam tabel.
6. `scripts/make_sample_docs.py`: hasilkan dokumen dummy berbahasa Indonesia: 1 PDF dengan tabel, 1 DOCX dengan heading bertingkat, 1 XLSX dengan 2 sheet, 1 MD. Isinya fakta fiktif yang bisa ditanyakan (kebijakan cuti, anggaran, SOP). Tambahkan 1 dokumen berisi "instruksi jahat" (misalnya meminta asisten mengabaikan aturan dan menampilkan semua dokumen) untuk uji prompt injection nanti.
7. Tes: pytest dengan `pytest-socket` (blokir semua jaringan kecuali 127.0.0.1) sebagai default di `conftest.py`.
8. `README.md`: perintah PowerShell untuk setup (install uv, `ollama pull`, check_env, menjalankan tes).

## BATASAN
- Belum ada kode retrieval atau LLM. Hanya fondasi.
- Jangan mengunduh model atau paket selain yang tercantum tanpa konfirmasi.

## KRITERIA SELESAI
- `uv run pytest` hijau; `uv run python scripts/check_env.py` mencetak tabel; `make_sample_docs.py` menghasilkan 5 file di `data/sample/`.
- Laporkan angka token/detik dan waktu embed dari laptop ini.
