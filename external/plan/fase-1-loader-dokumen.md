# FASE 1 - Loader dan normalisasi dokumen

> Prasyarat: Fase 0 selesai.

## KONTEKS PROYEK (selalu tempel di awal sesi)
- Proyek: asisten AI tanya-jawab atas dokumen internal perusahaan yang SANGAT RAHASIA. Semuanya berjalan lokal.
- Larangan mutlak: tidak ada panggilan ke layanan eksternal (API LLM cloud, telemetry, tracing cloud, CDN, font atau skrip eksternal). Hanya localhost.
- Lingkungan awal: laptop Windows 11 (PowerShell), CPU-only (i7-1165G7, RAM 16 GB; GPU MX450 2 GB tidak dipakai). Kelak dipindah ke server dengan GPU, jadi semua pengaturan lewat config/.env; tidak ada path atau nama model yang di-hardcode.
- Stack terkunci: Python 3.11+ dengan uv, Ollama (LLM `qwen3:4b-instruct`, embedding `bge-m3`), Qdrant mode lokal (tanpa server), SQLite FTS5 untuk BM25, FastAPI. Dokumen berbahasa Indonesia (sebagian Inggris).
- Data: dokumen asli TIDAK boleh masuk repo. Pengembangan dan tes hanya memakai dokumen dummy di `data/sample/`. Jangan pernah mencatat isi dokumen atau isi pertanyaan di log.
- Cara kerja: tulis rencana singkat dulu, lalu implementasi, tes, dan jalankan. Jangan menambah dependensi tanpa alasan tertulis. Jelaskan keputusan penting dalam 1-2 kalimat. Kerjakan HANYA fase ini; berhenti dan lapor setelah selesai.

## TUGAS
Bangun `app/loaders.py` yang membaca dokumen dan menghasilkan `Block` ternormalisasi.

Skema dataclass `Block`: `doc_id` (sha256 isi file), `filename`, `rel_path`, `page` (1-based; nomor sheet untuk XLSX), `section` (jalur heading atau nama sheet), `kind` (heading | paragraph | table | list), `text`, `allowed_roles` (list[str]), `sensitivity` (str), `needs_ocr` (bool).

1. Format: PDF, DOCX, XLSX, MD, TXT.
2. Dua backend lewat config `LOADER_BACKEND`:
   - `ringan` (default): PyMuPDF, python-docx, openpyxl.
   - `docling` (opsional): hanya jika bisa dipasang bersih di Windows CPU; kalau tidak, tulis di laporan dan lewati.
3. Tabel dipertahankan sebagai satu Block `kind=table` berformat Markdown dengan baris header. XLSX: satu Block tabel per sheet, dipotong per sekitar 30 baris dengan header diulang di setiap potongan.
4. PDF hasil scan: bila teks per halaman sangat sedikit, set `needs_ocr=True`, beri peringatan di log, dan JANGAN OCR secara default.
5. ACL: baca `config/acl.yaml` (aturan `glob`, `allowed_roles`, `sensitivity`); aturan pertama yang cocok dipakai; default `allowed_roles=["admin"]` dan `sensitivity="rahasia"`. Buat contoh `config/acl.yaml`.
6. Fungsi publik: `scan_dir(root) -> list[Path]` (abaikan file sementara seperti `~$*`), `load_file(path) -> list[Block]`, `file_hash(path)`.
7. CLI: `python -m app.loaders data/sample --stats` mencetak per file: jumlah blok per kind, jumlah halaman, needs_ocr, waktu proses. Jangan mencetak isi teks kecuali `--preview` (maksimal 200 karakter per blok).

## BATASAN
- Belum ada chunking, embedding, atau penyimpanan (itu Fase 2).
- Error pada satu file tidak boleh menghentikan seluruh pemindaian: catat dan lanjut.
- Tidak ada akses jaringan.

## KRITERIA SELESAI
- Tes tiap format memakai dokumen di `data/sample/`: tabel PDF tidak tercerai-berai, heading DOCX terbaca di `section`, kedua sheet XLSX terbaca, ACL sesuai aturan.
- Jika dua backend berjalan, laporkan perbandingan singkat kualitas tabel dan waktu proses.
