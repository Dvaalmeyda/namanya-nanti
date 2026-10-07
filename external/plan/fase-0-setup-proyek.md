# FASE 0 - Setup proyek dan lingkungan

> Prasyarat: Ollama terpasang; `ollama pull qwen3:4b-instruct` dan `ollama pull bge-m3` sudah dijalankan.
> Baca `00-KONTEKS.md` terlebih dahulu.

## TUGAS
Siapkan fondasi proyek di **root workspace** dan pastikan lingkungan lokal berfungsi serta terukur.

1. **Paket dan repo**
   - `pyproject.toml` dengan `uv` (Python 3.11+), dependensi inti dari daftar di `00-KONTEKS.md`; dependensi dev (`pytest`, `pytest-socket`, `httpx`) di grup terpisah.
   - Hapus `requirements.txt` (digantikan `pyproject.toml` + `uv.lock`). `.venv` yang ada boleh dipakai ulang oleh uv.
   - Buat folder: `app/`, `app/api/routes/`, `eval/`, `scripts/`, `tests/`, `data/sample/`, `data/docs/`, `data/index/`.
   - Tambahkan ke `.gitignore`: `data/docs/`, `data/index/`, `eval/reports/`, `eval/*.private.*`. Pastikan `.env` tetap diabaikan. Periksa bahwa pola yang sudah ada (misalnya `lib/`) tidak ikut mengabaikan folder proyek.

2. **`app/config.py`** (pydantic-settings, baca `.env`). Field inti beserta default:
   - Ollama: `OLLAMA_HOST=http://127.0.0.1:11434`, `OLLAMA_TIMEOUT_S=120`, `KEEP_ALIVE=30m`, `NUM_THREAD=None` (None = otomatis).
   - LLM: `LLM_MODEL=qwen3:4b-instruct`, `LLM_THINK=false`, `NUM_CTX=4096`, `NUM_PREDICT=384`, `TEMPERATURE=0.1`.
   - Embedding: `EMBED_MODEL=bge-m3`, `EMBED_QUERY_PREFIX=""`, `EMBED_DOC_PREFIX=""`, `EMBED_BATCH=16`.
   - Path: `DOCS_DIR=data/docs`, `SAMPLE_DIR=data/sample`, `INDEX_DIR=data/index`.
   - Privasi: `ALLOW_REMOTE=false`, `LOG_CONTENT=false`, `LOG_LEVEL=INFO`.
   - Fase berikutnya menambah field-nya sendiri (chunking, retrieval, API). Sediakan `.env.example` dengan komentar singkat per field.
   - Singleton `get_settings()` (cache) agar mudah di-override di tes.

3. **`app/logging_setup.py`**: logging terstruktur (key=value atau JSON) ke console dan file `data/index/app.log` dengan rotasi. Filter yang membuang field `text`, `question`, `answer`, `context` kecuali `LOG_CONTENT=true`.

4. **`app/privacy.py`**:
   - `apply_offline_env()`: set `ANONYMIZED_TELEMETRY=False`, `DO_NOT_TRACK=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.
   - `assert_local_only(url)`: tolak host selain `127.0.0.1`, `::1`, `localhost` kecuali `ALLOW_REMOTE=true`. Dipanggil untuk `OLLAMA_HOST` saat startup.

5. **`app/ollama_client.py`**: satu-satunya pintu ke Ollama.
   - `get_client()` dengan host dan timeout dari config.
   - `embed(texts, kind: "query" | "doc") -> list[list[float]]`: menambahkan `EMBED_QUERY_PREFIX` atau `EMBED_DOC_PREFIX`, batching, retry dengan backoff, dan `keep_alive`.
   - `chat(messages, stream: bool)`: meneruskan `think=LLM_THINK`, `keep_alive`, serta options `num_ctx`, `num_predict`, `temperature`, `num_thread` (bila diset). Kembalikan teks/stream beserta metrik dari respons (`prompt_eval_count`, `prompt_eval_duration`, `eval_count`, `eval_duration`, `load_duration`).
   - `warmup()`: memuat LLM dan model embedding ke memori dengan permintaan minimal.
   - `list_models()` dan `loaded_models()` (dari `/api/ps`, termasuk `size` dan `size_vram`).
   - Error ramah: kelas `OllamaUnavailable` dan `ModelNotFound` dengan pesan berisi perintah perbaikan (misalnya `ollama pull ...`).

6. **`scripts/check_env.py`**: cetak tabel berisi:
   - Ollama dapat dihubungi; model LLM dan embedding tersedia (jika tidak, cetak perintah `ollama pull ...`).
   - **Prefill** (token/detik prompt) dengan prompt sekitar 1.000 token, dari `prompt_eval_count / prompt_eval_duration`.
   - **Generate** (token/detik) dari `eval_count / eval_duration` untuk sekitar 150 token.
   - Waktu muat model (`load_duration`) saat dingin vs hangat.
   - Waktu embed 16 kalimat (dingin dan hangat) dan dimensi vektor.
   - **Pembagian CPU/GPU** dari `/api/ps` (`size_vram / size`).
   - Opsi `--num-thread 4 8` untuk membandingkan jumlah thread; `--models a b` untuk membandingkan beberapa LLM yang sudah di-pull.
   - Panduan di README: untuk mengukur mode CPU-only, jalankan ulang server Ollama dengan `$env:CUDA_VISIBLE_DEVICES="-1"` lalu ulangi `check_env.py`.

7. **`scripts/make_sample_docs.py`**: hasilkan dokumen dummy pribadi berbahasa Indonesia di `data/sample/` dengan fakta fiktif yang bisa ditanyakan:
   - `asuransi/polis-kesehatan.pdf`: 2-3 halaman, ada tabel manfaat (jenis manfaat, limit, keterangan). Buat dengan PyMuPDF (`Story`/`insert_htmlbox`), tanpa dependensi baru.
   - `rumah/kontrak-sewa.docx`: heading bertingkat (Pasal 1, Pasal 2 > Pembayaran, dsb.) dan satu tabel jadwal pembayaran di tengah teks.
   - `keuangan/anggaran-rumah-tangga.xlsx`: 2 sheet ("Pengeluaran 2025", "Tabungan"). **Tulis nilai, bukan rumus** (file buatan openpyxl tidak menyimpan nilai cache rumus).
   - `kendaraan/catatan-servis.md`: riwayat servis dengan tanggal, kilometer, biaya, dan kode suku cadang (untuk menguji pencarian leksikal).
   - `unduhan/artikel-tips.txt`: dokumen berisi "instruksi jahat" (meminta asisten mengabaikan aturan, membuka prompt sistem, dan menampilkan semua dokumen) untuk uji prompt injection.
   - `arsip/polis-kesehatan.pdf`: salinan identik (nama sama, folder berbeda) dari PDF di atas, untuk menguji dokumen kembar di path berbeda dan pemakaian ulang embedding.

8. **Tes**: `tests/conftest.py` mengaktifkan pytest-socket secara default dengan host yang diizinkan `127.0.0.1`, `::1`, `localhost`. Tes untuk `assert_local_only`, filter log, dan `embed()` yang menambahkan prefix sesuai `kind` (klien Ollama di-mock).

9. **`README.md`**: perintah PowerShell untuk instal uv, `uv sync`, `ollama pull`, menyalin `.env.example` ke `.env`, `check_env`, `make_sample_docs`, dan `uv run pytest`. Sertakan rekomendasi variabel server Ollama untuk laptop ini: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=2`.

## BATASAN
- Belum ada kode loader, indexing, retrieval, atau API. Hanya fondasi dan klien Ollama.
- Jangan mengunduh model atau paket selain yang tercantum tanpa konfirmasi.

## KRITERIA SELESAI
- `uv run pytest` hijau; `uv run python scripts/check_env.py` mencetak tabel; `make_sample_docs.py` menghasilkan 6 file di subfolder `data/sample/`.
- Laporkan dari laptop ini: prefill token/detik, generate token/detik, waktu muat dingin, waktu embed 16 kalimat, persentase GPU, dan perbandingan `num_thread` 4 vs 8. Bila sempat, sertakan angka mode CPU-only.
