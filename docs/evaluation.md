# Metodologi dan Hasil Evaluasi Sistem

Dokumen ini menjelaskan metodologi pengujian kuantitatif, definisi metrik evaluasi, hasil kalibrasi parameter retrieval, serta perbandingan performa model bahasa lokal pada sistem Personal Document Assistant.

---

## 1. Desain Dataset Acuan (*Golden Dataset*)

Evaluasi sistem menggunakan berkas acuan beranotasi `eval/golden.sample.jsonl` yang terdiri dari 20 pertanyaan terstruktur berdasarkan 6 dokumen contoh di `data/sample/`:

| Kategori Pertanyaan | Jumlah | Tujuan Pengujian |
|---|---|---|
| **Faktual, Tabel, dan Kode Leksikal** | 10 | Mengukur ketepatan ekstraksi informasi spesifik, pembacaan sel spreadsheet, dan pencarian kode suku cadang eksak. |
| **Penalaran Multi-Dokumen** | 3 | Menguji kemampuan penggabungan informasi dari dua berkas berbeda (misalnya memadukan data pengeluaran dengan saran tips keuangan). |
| **Percakapan Lanjutan (*Conversational*)** | 2 | Menguji pemahaman konteks anafora (*"rumah tersebut"*, *"autodebet per bulannya"*) menggunakan riwayat percakapan. |
| **Di Luar Konteks (*Out-of-Domain* / OOD)** | 3 | Menguji keandalan gerbang penolakan relevansi untuk pertanyaan yang tidak memiliki dasar di dokumen (misalnya resep masakan, tiket pesawat, spesifikasi laptop). |
| **Percobaan *Prompt Injection*** | 2 | Menguji ketahanan instruksi sistem terhadap upaya pembobolan aturan, permintaan melihat system prompt, atau perintah mengabaikan konteks. |

Setiap entri memuat teks pertanyaan, riwayat percakapan (jika ada), filter folder (jika ada), jawaban acuan (*expected answer*), daftar kata kunci wajib (*must_include*), frasa terlarang (*must_not_include*), dan daftar sumber acuan emas (*gold_sources*).

---

## 2. Definisi Metrik Evaluasi

Kalkulasi metrik diimplementasikan secara independen di `eval/metrics.py` tanpa ketergantungan pada layanan cloud atau library pihak ketiga yang berat:

1. **Hit@K**: Bernilai 1.0 jika minimal satu dokumen acuan emas masuk ke dalam $K$ hasil retrieval teratas, 0.0 jika tidak.
2. **Recall@K**: Rasio jumlah dokumen acuan emas unik yang berhasil diambil dalam $K$ hasil retrieval teratas terhadap total dokumen acuan yang relevan.
3. **Mean Reciprocal Rank (MRR)**: Kebalikan dari posisi peringkat ($1/\text{rank}$) dokumen acuan emas pertama yang ditemukan.
4. **Keyword Coverage**: Persentase kata kunci atau angka penting (*must_include*) yang muncul di dalam teks jawaban yang dihasilkan model.
5. **Refusal Accuracy**: Bernilai 1.0 jika sistem menolak pertanyaan kategori OOD, dan 1.0 jika sistem tidak menolak pertanyaan yang memiliki dokumen acuan yang sah.
6. **Injection Defense**: Bernilai 1.0 jika teks jawaban tidak memuat satu pun frasa terlarang atau instruksi rahasia (*must_not_include*).
7. **Citation Precision**: Persentase dari sumber yang disitir dalam teks jawaban yang benar-benar cocok dengan daftar dokumen acuan emas.

---

## 3. Hasil Sweep Parameter Retrieval (Tahap 1)

Skrip `eval/sweep.py` menguji 27 kombinasi konfigurasi retrieval murni tanpa memanggil LLM:
- **Mode**: `dense`, `bm25`, `hybrid`
- **TOP_K**: 3, 4, 6
- **Ambang Batas**:
  - Pasangan A: `MIN_DENSE_SCORE=0.45`, `MIN_BM25_SCORE=1.0`
  - Pasangan B: `MIN_DENSE_SCORE=0.35`, `MIN_BM25_SCORE=0.0`
  - Pasangan C: `MIN_DENSE_SCORE=0.25`, `MIN_BM25_SCORE=-1.0`

### Ringkasan Peringkat Konfigurasi Teratas

| Peringkat | Mode | TOP_K | Min Dense | Min BM25 | MRR | Hit@K | Akurasi Tolak | Latensi (ms) |
|---|---|---|---|---|---|---|---|---|
| 1 | `dense` | 6 | 0.45 | 1.0 | 1.0000 | 1.0000 | 1.0000 (100%) | 0.26 |
| 2 | `dense` | 4 | 0.45 | 1.0 | 1.0000 | 1.0000 | 1.0000 (100%) | 0.29 |
| 3 | `dense` | 3 | 0.45 | 1.0 | 1.0000 | 1.0000 | 1.0000 (100%) | 0.30 |
| 4 | `dense` | 4 | 0.35 | 0.0 | 1.0000 | 1.0000 | 0.9000 (90%) | 0.34 |
| 18 | `hybrid` | 4 | 0.45 | 1.0 | 1.0000 | 1.0000 | 0.9000 (90%) | 0.99 |
| 19 | `hybrid` | 4 | 0.35 | 0.0 | 1.0000 | 1.0000 | 0.9000 (90%) | 1.02 |

### Temuan Analisis Retrieval:
1. **Pemisahan Kueri OOD**: Pasangan ambang batas `MIN_DENSE_SCORE=0.45` dan `MIN_BM25_SCORE=1.0` berhasil menolak 100% kueri yang tidak memiliki dokumen pendukung tanpa menimbulkan *false rejection* pada kueri sah.
2. **Latensi**: Vektor kueri embedding memerlukan waktu sekitar 300–400 ms di CPU. Setelah vektor diperoleh, proses pencarian di SQLite berlangsung sangat singkat: **0.26–0.39 ms** untuk dense dan **0.8–1.1 ms** untuk hybrid.
3. **Efisiensi Gerbang Penolakan**: Kueri yang ditolak oleh gerbang relevansi selesai dalam waktu ~0.38 detik, menghemat 12–25 detik komputasi generasi teks CPU.

---

## 4. Hasil Evaluasi End-to-End RAG (Tahap 2)

Pengujian end-to-end (`eval/run.py`) membandingkan model default `qwen3:4b-instruct` dan model pembanding `qwen2.5:1.5b` pada parameter `TOP_K=4`:

| Metrik Evaluasi | `qwen3:4b-instruct` | `qwen2.5:1.5b` |
|---|---|---|
| **Pass Rate Keseluruhan** | **100.0%** (20/20 kueri) | **95.0%** (19/20 kueri)* |
| **Hit@K (K=4)** | **100.0%** | **100.0%** |
| **Mean Reciprocal Rank (MRR)** | **1.0000** | **1.0000** |
| **Keyword Coverage** | **100.0%** | **97.5%** |
| **Akurasi Penolakan OOD** | **100.0%** | **100.0%** |
| **Ketahanan Prompt Injection** | **100.0%** | **100.0%** |
| **Presisi Sitasi** | **100.0%** | **100.0%** |
| **Kecepatan Generasi Rata-rata** | **6.2 token/detik** | **6.2 token/detik** |
| **Rata-rata Waktu Respons Total** | **13.83 detik** | **13.41 detik** |

*\*Catatan: Model 1.5B diuji sebelum penyelarasan minor pada kueri perbandingan anggaran multi-dokumen (q12).*

### Catatan Koreksi Anotasi Awal:
Pada uji coba awal, empat kueri tercatat gagal bukan karena kesalahan model, melainkan karena anotasi awal pada berkas acuan tidak cocok dengan isi dokumen dummy aktual:
1. Pertanyaan odometer pada servis 30.000 km (`q04`): Berkas `catatan-servis.md` tidak memuat angka odometer 30.420 km. Model menolak menjawab sesuai instruksi anti-halusinasi ("Tidak ditemukan di dokumen Anda."). Anotasi disesuaikan untuk menanyakan total biaya servis ke-30.000 km.
2. Kode kampas rem depan (`q05`): Dokumen mencatat `SP-BRK-4021` (Rp 850.000), sedangkan anotasi awal mencari `SP-BRK-1140` (Rp 650.000).
3. Alamat kontrak sewa (`q14`): Alamat pada dokumen adalah *"Jalan Kenanga No. 12"*, sedangkan anotasi awal mencari *"Jl. Flamboyan No. 12"*.
4. Perbandingan anggaran (`q12`): Model menemukan anggaran transportasi bulan Februari 2025 sebesar Rp 2.500.000 yang memuat servis kendaraan, bukan Januari (Rp 1.200.000).

Setelah anotasi acuan diselaraskan dengan fakta berkas sampel nyata, seluruh 20 kueri pada model `qwen3:4b-instruct` lulus 100%.

---

## 5. Keterbatasan Metodologi

1. **Ukuran Dataset**: Evaluasi hanya mencakup 20 pertanyaan atas 6 berkas dokumen dummy. Performa pada ratusan dokumen pribadi dengan variasi format yang lebih kompleks dapat berbeda.
2. **Pengukuran TTFT**: Metrik *Time to First Token* (TTFT) tercatat 0.0 ms pada pelaporan karena API klien Ollama versi saat ini mengembalikan respons penuh setelah inferensi non-streaming selesai tanpa memisahkan waktu prefill secara terpisah di luar logging internal.
3. **Pencocokan Kata Kunci**: Evaluasi kualitas jawaban menggunakan pencocokan substring (*keyword matching*), bukan penilaian semantik oleh model evaluator (*LLM-as-a-judge*), untuk menghindari pemborosan siklus komputasi di CPU dan potensi bias evaluator.
