# FASE 2 - Indexing (app/store.py + app/indexing.py)

> Prasyarat: Fase 1 selesai (`Block` tersedia).
> Baca `00-KONTEKS.md` terlebih dahulu.

## TUGAS
Bangun penyimpanan dan pipeline indexing di dua file:
- `app/store.py`: skema SQLite, operasi baca/tulis, pencarian BM25, dan indeks vektor numpy di memori. Dipakai ulang oleh retrieval dan API.
- `app/indexing.py`: chunking, embedding, sinkronisasi incremental, dan CLI.

Target masing-masing di bawah sekitar 400 baris, fungsi kecil dan bernama jelas.

### 1. Identitas
- `doc_id = sha1(rel_path)[:16]`: stabil selama path tidak berubah. **Jangan** memakai hash isi sebagai identitas (dua file kembar akan bertabrakan).
- `chunk_id = f"{doc_id}:{index:04d}"`.

### 2. Chunking sadar struktur
- Gabungkan blok berurutan dalam `section` yang sama sampai sekitar `CHUNK_SIZE` karakter (default 800) dengan overlap `CHUNK_OVERLAP` (default 100). Jangan menggabungkan blok lintas halaman PDF bila itu membuat label lokasi ambigu (ambil halaman pertama dan simpan `page_end`).
- Blok `table` tidak boleh terpotong di tengah baris; bila terlalu panjang, potong per kelompok baris dan ulangi header.
- Awali teks chunk yang dikirim ke embedding dengan konteks ringkas `filename > section` agar chunk pendek tetap bermakna. Teks yang disimpan dan ditampilkan tetap teks asli.
- Setiap chunk membawa: `chunk_id`, `doc_id`, `idx`, `page`, `page_end`, `sheet`, `section`, `kind`, `location` (dari `format_location`), `text`.

### 3. Skema SQLite (`INDEX_DIR/index.db`, `journal_mode=WAL`, `foreign_keys=ON`)
- `documents(doc_id PK, rel_path UNIQUE, filename, file_type, folder, file_hash, size, mtime, n_chunks, needs_ocr, indexed_at)`; indeks pada `file_hash`.
- `chunks(rowid INTEGER PK, chunk_id UNIQUE, doc_id FK ON DELETE CASCADE, idx, page, page_end, sheet, section, kind, location, text, embedding BLOB)`. Embedding disimpan sebagai float32 `tobytes()`.
- `chunks_fts`: tabel FTS5 biasa (bukan external content, agar tidak perlu trigger) dengan kolom `fts_text`, `rowid` sama dengan `chunks.rowid`, tokenizer `unicode61 remove_diacritics 2`. `fts_text` = `filename + section + text` setelah normalisasi (huruf kecil; di-stem bila `STEMMER=sastrawi`).
- `settings(key PK, value)`: `embed_model`, `embed_dim`, `embed_doc_prefix`, `chunk_size`, `chunk_overlap`, `stemmer`, `schema_version`, `index_version` (dinaikkan di setiap commit yang mengubah data).

### 4. Embedding
- Lewat `ollama_client.embed(texts, kind="doc")` dengan batch `EMBED_BATCH`, retry, timeout, dan progress bar `tqdm` beserta ETA.
- Hitung embedding **sebelum** membuka transaksi tulis, agar lock SQLite tidak tertahan selama embedding berjalan.
- **Pakai ulang embedding**: bila `file_hash` dan `filename` sudah ada di index (file dipindah ke folder lain atau disalin) dan pengaturan embedding sama, salin chunk dan vektor dari dokumen tersebut tanpa memanggil embedding. File yang diganti nama di-embed ulang, karena nama file ikut masuk ke teks yang di-embed.

### 5. Indeks vektor di memori (`store.VectorIndex`)
- Muat semua embedding menjadi matriks numpy `(N, D)` beserta array `rowid`, `doc_id`, `folder`, `file_type` untuk filter.
- `search(query_vec, k, mask=None) -> list[(rowid, score)]`: dot product (vektor sudah ternormalisasi; verifikasi sekali dan normalisasi bila belum), `argpartition` untuk top-k.
- Opsi `VECTOR_DTYPE=float32|float16` untuk menghemat RAM.
- `refresh_if_stale()`: muat ulang bila `index_version` di database berubah.

### 6. Pencarian BM25 (`store.bm25_search`)
- `build_fts_query(text)`: tokenisasi dengan regex kata, huruf kecil, buang stopword bahasa Indonesia yang umum (daftar kecil di kode), deduplikasi, **kutip setiap token** (`"token"`), gabung dengan `OR`. Hasil kosong berarti BM25 dilewati. Fungsi ini wajib aman terhadap input berisi `"`, `-`, `:`, `*`, `(`, `)`, dan kata `AND/OR/NOT/NEAR`.
- Filter folder/tipe/doc_id lewat JOIN ke `chunks`/`documents` di kueri yang sama.
- Kembalikan skor positif (`-bm25(chunks_fts)`, karena FTS5 memberi nilai negatif untuk kecocokan lebih baik).

### 7. Sinkronisasi incremental
- Bandingkan hasil `scan_dir` dengan tabel `documents` berdasarkan `rel_path`:
  - Baru: index. Hash berubah: hapus chunk lama lalu index ulang. Hilang dari disk: hapus. Tidak berubah: lewati tanpa memanggil embedding.
  - Jalur cepat: bila `size` dan `mtime` sama dengan yang tercatat, anggap tidak berubah tanpa menghitung hash. Hash hanya dihitung bila salah satunya berbeda.
- Satu dokumen = satu transaksi (hapus lama + sisipkan baru + update `documents` + naikkan `index_version`). Kegagalan di tengah dokumen = rollback dokumen itu saja, catat, lanjut ke dokumen berikutnya.
- Jika `settings` berbeda dari konfigurasi sekarang (model embedding, prefix, ukuran chunk, stemmer), tolak `update` dan minta `rebuild`.
- Hanya satu proses indexing pada satu waktu: file lock `INDEX_DIR/.indexing.lock` (stale lock dideteksi dari PID). Pembaca (API) tetap bisa membaca selama indexing berkat WAL.
- Fungsi inti `sync(root, progress_cb=None) -> SyncReport` (jumlah baru/berubah/dihapus/dilewati/gagal, durasi, chunk per detik) agar dapat dipanggil dari CLI maupun API.

### 8. CLI `python -m app.indexing`
- `build` / `update` (sama-sama memanggil `sync`), `rebuild` (kosongkan semua tabel dalam satu transaksi, tulis ulang `settings`, lalu `sync`).
- `status`: jumlah dokumen, chunk, ukuran file database, perkiraan RAM matriks vektor, `embed_model`, dokumen `needs_ocr`.
- `search "kueri" [--folder X] [--k 5]`: debug, tampilkan hasil dense dan BM25 terpisah beserta skor; teks dipotong 150 karakter.
- Opsi `--root` (default `DOCS_DIR`); gunakan `--root data/sample` untuk pengembangan.

## BATASAN
- Tidak ada reranker, LLM, atau API di fase ini.
- Log hanya berisi angka, ID, dan nama file, tidak pernah isi chunk.
- Jangan menambah vector store atau framework lain.

## KRITERIA SELESAI
- Tes (embedding di-mock):
  - Idempotent: `sync` dua kali, run kedua tidak memanggil embedding.
  - File berubah: chunk lama terganti. File dihapus: bersih dari `documents`, `chunks`, `chunks_fts`, dan matriks setelah refresh.
  - Dua file kembar menjadi dua dokumen berbeda; dokumen kedua memakai ulang embedding (embedding tidak dipanggil untuknya).
  - File dipindah ke folder lain: tidak memanggil embedding.
  - Tabel tidak terpotong di tengah baris.
  - `build_fts_query` aman untuk input berisi karakter khusus dan operator FTS5 (tidak melempar error).
  - Kegagalan embedding di tengah dokumen tidak meninggalkan state setengah jadi.
- Jalankan `build --root data/sample` dengan model sungguhan dan laporkan: jumlah chunk, chunk per detik di laptop ini, ukuran database, serta 3 contoh hasil `search` (termasuk satu kueri kode suku cadang dari `catatan-servis.md`).
