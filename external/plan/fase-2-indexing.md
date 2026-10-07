# FASE 2 - Indexing (satu file: app/indexing.py)

> Prasyarat: Fase 1 selesai (`Block` tersedia).

## KONTEKS PROYEK (selalu tempel di awal sesi)
- Proyek: asisten AI tanya-jawab atas dokumen internal perusahaan yang SANGAT RAHASIA. Semuanya berjalan lokal.
- Larangan mutlak: tidak ada panggilan ke layanan eksternal (API LLM cloud, telemetry, tracing cloud, CDN, font atau skrip eksternal). Hanya localhost.
- Lingkungan awal: laptop Windows 11 (PowerShell), CPU-only (i7-1165G7, RAM 16 GB; GPU MX450 2 GB tidak dipakai). Kelak dipindah ke server dengan GPU, jadi semua pengaturan lewat config/.env; tidak ada path atau nama model yang di-hardcode.
- Stack terkunci: Python 3.11+ dengan uv, Ollama (LLM `qwen3:4b-instruct`, embedding `bge-m3`), Qdrant mode lokal (tanpa server), SQLite FTS5 untuk BM25, FastAPI. Dokumen berbahasa Indonesia (sebagian Inggris).
- Data: dokumen asli TIDAK boleh masuk repo. Pengembangan dan tes hanya memakai dokumen dummy di `data/sample/`. Jangan pernah mencatat isi dokumen atau isi pertanyaan di log.
- Cara kerja: tulis rencana singkat dulu, lalu implementasi, tes, dan jalankan. Jangan menambah dependensi tanpa alasan tertulis. Jelaskan keputusan penting dalam 1-2 kalimat. Kerjakan HANYA fase ini; berhenti dan lapor setelah selesai.

## TUGAS
Bangun SELURUH logika indexing dalam SATU file: `app/indexing.py` (target kurang dari 500 baris, fungsi kecil dan bernama jelas). Input: `Block` dari Fase 1.

1. Chunking sadar struktur: gabungkan blok berurutan dalam `section` yang sama sampai sekitar 800 karakter dengan overlap sekitar 100 (config `CHUNK_SIZE`, `CHUNK_OVERLAP`). Blok `table` tidak boleh terpotong di tengah baris; bila terlalu panjang, potong per kelompok baris dan ulangi header. Setiap chunk membawa: `chunk_id` (stabil: `{doc_id}:{index}`), doc_id, filename, rel_path, page, section, kind, text, allowed_roles, sensitivity.
2. Embedding: `ollama.embed(model=EMBED_MODEL, input=batch)` dengan batch configurable (default 16), normalisasi L2, retry dengan backoff, timeout, dan progress bar dengan ETA.
3. Penyimpanan:
   - SQLite (`data/index/meta.db`): tabel `chunks` (sumber kebenaran teks dan metadata), tabel virtual FTS5 untuk BM25 (tokenizer unicode61 dengan remove_diacritics), tabel `manifest` (doc_id, rel_path, hash, mtime, n_chunks, indexed_at), tabel `settings` (embed_model, embed_dim, chunk_size, chunk_overlap).
   - Qdrant mode lokal (`path=data/index/qdrant`, cosine): vektor dengan id deterministik dari chunk_id, payload hanya `chunk_id`, `doc_id`, `allowed_roles`.
   - Qdrant mode lokal hanya dapat dibuka satu proses pada satu waktu: deteksi lock dan tampilkan pesan yang jelas.
4. Incremental: bandingkan hash file dengan manifest. Berubah: hapus chunk lama (SQLite dan Qdrant) lalu index ulang. Hilang: hapus. Tidak berubah: lewati tanpa memanggil embedding. Jika `settings` berbeda dari konfigurasi sekarang, tolak `update` dan minta `rebuild`.
5. CLI `python -m app.indexing`: `build`, `update`, `rebuild`, `status` (jumlah dokumen, jumlah chunk, ukuran index, embed_model), dan `search "kueri" --role X --k 5` (hanya untuk debug: tampilkan hasil dense dan BM25 terpisah beserta skor; teks dipotong 150 karakter).
6. Gunakan transaksi: kegagalan di tengah proses tidak boleh meninggalkan state setengah jadi di kedua store.

## BATASAN
- Tidak ada reranker, LLM, atau API di fase ini.
- Log hanya berisi angka dan ID, tidak pernah isi chunk.
- Jangan menambah vector store atau framework lain (tanpa LangChain/LlamaIndex).

## KRITERIA SELESAI
- Tes (embedding di-mock): idempotent (jalan 2x, run kedua tidak memanggil embedding), file berubah terganti, file dihapus bersih, tabel tidak terpotong, ACL tersimpan di kedua store.
- Jalankan `build` pada `data/sample/` dan laporkan: jumlah chunk, chunk per detik di laptop ini, ukuran index, serta 3 contoh hasil `search`.
