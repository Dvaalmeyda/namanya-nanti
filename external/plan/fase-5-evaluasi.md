# FASE 5 - Evaluasi dan kalibrasi

> Prasyarat: Fase 4 selesai (API dan seluruh pipeline RAG sudah berfungsi).
> Baca `00-KONTEKS.md` terlebih dahulu.

## TUGAS
Bangun harness evaluasi di folder `eval/` untuk mengukur kualitas dan performa (latensi) secara sistematis, serta menentukan konfigurasi terbaik (model LLM, model embedding, ukuran chunk, TOP_K, ambang penolakan).

### 1. Golden Set (`eval/golden.sample.jsonl`)
Buat 20 contoh pertanyaan berbasis dokumen dummy di `data/sample/`:
- Format per baris:
  - `id`: identifier unik (misal `q01`)
  - `question`: pertanyaan pengguna
  - `type`: `faktual` | `tabel` | `kode_leksikal` | `multi_dokumen` | `lanjutan` | `tidak_ada_jawaban` | `injection`
  - `history`: daftar giliran percakapan sebelumnya (khusus tipe `lanjutan`, kosong untuk lainnya)
  - `filters`: filter folder/tipe jika relevan
  - `expected_answer`: jawaban acuan singkat
  - `must_include`: daftar kata/frasa/angka penting yang wajib ada
  - `must_not_include`: kata/frasa yang dilarang muncul (termasuk kebocoran prompt sistem pada tipe injection)
  - `gold_sources`: daftar `{rel_path, location}` acuan
- Distribusi:
  - 10 pertanyaan faktual/tabel/kode (termasuk kode suku cadang dari `catatan-servis.md` dan tabel dari PDF/XLSX)
  - 3 pertanyaan perbandingan atau multi-dokumen
  - 2 pertanyaan lanjutan (memanfaatkan `history`)
  - 3 pertanyaan di luar isi dokumen (tipe `tidak_ada_jawaban`, wajib dijawab penolakan)
  - 2 uji prompt injection (menyasar file `artikel-tips.txt`, asisten tidak boleh membocorkan prompt atau mengabaikan aturan)
- Dokumen/pertanyaan pribadi asli disimpan di `eval/golden.private.jsonl` (di-gitignore).

### 2. Metrik Pengukuran
- **Retrieval (tanpa LLM)**:
  - `Hit@K`: apakah dokumen acuan masuk dalam top-K
  - `Recall@K`: proporsi potongan acuan yang berhasil diambil
  - `MRR` (Mean Reciprocal Rank): posisi peringkat sumber acuan pertama
- **Jawaban RAG**:
  - `Akurasi Penolakan`: 100% pada tipe `tidak_ada_jawaban` harus menghasilkan `refused=True`
  - `Ketahanan Injection`: 0% kebocoran prompt atau pelanggaran aturan pada tipe `injection`
  - `Cakupan Kunci`: persentase kata di `must_include` yang muncul di jawaban
  - `Presisi Sitasi`: apakah sumber yang disitasi benar-benar relevan
- **Performa & Latensi**:
  - `Embed Query Latency (ms)`
  - `Search Latency (ms)`
  - `TTFT / Prefill Latency (ms)`
  - `Generation Speed (token/detik)`
  - `Total Latency (detik)`

### 3. Alur Evaluasi Dua Tahap (Hemat Waktu di CPU)
Karena menjalankan LLM di CPU memakan waktu puluhan detik per pertanyaan, evaluasi dibagi menjadi dua tahap:

- **Tahap 1: Sweep Retrieval Murni (`python -m eval.sweep --stage retrieval`)**
  - Berjalan dalam hitungan detik karena tidak memanggil LLM.
  - Membandingkan:
    - Mode retrieval: `hybrid` vs `dense` vs `bm25`
    - Model embedding: `bge-m3` vs kandidat lain yang tersedia (`qwen3-embedding:0.6b`, `embeddinggemma`, dsb.)
    - Stemmer BM25: default vs Sastrawi
    - Ukuran chunk: 600 vs 800 vs 1200
    - Nilai `TOP_K`: 3 vs 4 vs 6
  - Output: ranking konfigurasi retrieval terbaik berdasarkan `MRR` dan `Hit@K`.

- **Tahap 2: Evaluasi End-to-End (`python -m eval.run`)**
  - Menguji kombinasi retrieval terbaik dari Tahap 1 dengan variasi model LLM (misalnya `qwen3:4b-instruct`, `qwen3.5:4b`, `gemma4:e4b`, `qwen3.5:2b`, `gemma4:e2b`).
  - Menguji opsi `QUERY_REWRITE=true` vs `false` pada pertanyaan tipe `lanjutan` (mengukur trade-off akurasi vs tambahan latensi 10-25 detik).
  - Mengkalibrasi ambang penolakan `MIN_DENSE_SCORE` dan `MIN_BM25_SCORE` agar tidak salah menolak pertanyaan valid namun tetap menolak pertanyaan di luar konteks.

### 4. Runner & Pelaporan
- `python -m eval.run --golden eval/golden.sample.jsonl --models qwen3:4b-instruct ... --k 4`:
  - Menjalankan pengujian dan menghasilkan laporan tabel Markdown serta CSV di `eval/reports/`.
  - Opsi `--show-failures` mencetak ringkasan kasus gagal (tanpa membocorkan data jika dijalankan pada set privat).
- `eval/README.md`: panduan cara membuat pertanyaan evaluasi untuk dokumen pribadi serta interpretasi metrik keseimbangan kualitas vs kecepatan.

## BATASAN
- Jangan commit file yang berisi pertanyaan atau jawaban dokumen pribadi nyata.
- Evaluasi berjalan langsung via modul Python internal (`retrieval.py` dan `rag.py`), tidak membebani network HTTP API.
- Tidak memakai library evaluasi berat berbasis cloud (Ragas/LangSmith); gunakan logika mandiri berbasis python dan pandas/csv.

## KRITERIA SELESAI
- File `eval/golden.sample.jsonl` berisi 20 pertanyaan siap pakai.
- Script sweep retrieval dan runner end-to-end berhasil dijalankan pada sample dataset.
- Tersedia tabel perbandingan minimal 2 model LLM di laptop ini yang memuat:
  - Skor retrieval dan akurasi jawaban.
  - Latensi per tahap (prefill, generate token/s, total waktu).
  - Rekomendasi konfigurasi default terbaik yang seimbang antara kualitas dan kecepatan untuk laptop ini.
