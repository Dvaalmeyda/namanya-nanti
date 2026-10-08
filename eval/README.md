# Panduan Evaluasi & Kalibrasi (Fase 5)

Direktori `eval/` memuat perangkat pengujian (*test harness*) mandiri untuk mengukur kualitas retrieval, akurasi jawaban, kepatuhan sitasi, serta profil latensi CPU secara kuantitatif.

---

## 1. Struktur Modul Evaluasi

- **`golden.sample.jsonl`**: Kumpulan 20 pertanyaan acuan berbasis berkas dummy di `data/sample/`.
- **`metrics.py`**: Fungsi kalkulasi metrik standar tanpa ketergantungan cloud (`Hit@K`, `Recall@K`, `MRR`, `Keyword Coverage`, `Refusal Accuracy`, `Injection Defense`, `Citation Precision`).
- **`sweep.py`**: Evaluasi Tahap 1 untuk sweep parameter retrieval murni secara cepat (tanpa memanggil LLM).
- **`run.py`**: Evaluasi Tahap 2 untuk pengujian end-to-end RAG (retrieval + inferensi LLM) dan pembuatan laporan.
- **`reports/`**: Direktori penyimpanan laporan Markdown dan CSV hasil evaluasi (di-gitignore).

---

## 2. Cara Menjalankan Evaluasi

### Tahap 1: Sweep Retrieval Cepat (Hitungan Detik)
Tahap ini menguji puluhan kombinasi parameter retrieval (`hybrid`, `dense`, `bm25`, `TOP_K`, dan ambang batas gerbang penolakan) tanpa memanggil LLM:
```powershell
uv run python -m eval.sweep --golden eval/golden.sample.jsonl
```
Hasil sweep akan menampilkan peringkat konfigurasi terbaik dan menyimpan laporannya di `eval/reports/sweep_retrieval_<timestamp>.md`.

### Tahap 2: Evaluasi End-to-End RAG
Tahap ini menguji pipeline RAG secara utuh menggunakan model Ollama lokal:
```powershell
# Evaluasi model default (qwen3:4b-instruct) dengan TOP_K=4
uv run python -m eval.run --golden eval/golden.sample.jsonl --models qwen3:4b-instruct --k 4 --show-failures
```

---

## 3. Membuat Dataset Evaluasi untuk Dokumen Pribadi

Untuk menguji performa asisten pada dokumen pribadi asli Anda tanpa membocorkan privasi ke repositori Git:
1. Buat berkas baru bernama `eval/golden.private.jsonl` (berkas ini sudah otomatis di-gitignore).
2. Tambahkan 15–20 pertanyaan acuan dengan format JSONL per baris:
```json
{
  "id": "priv_01",
  "question": "Berapa nomor polis asuransi jiwa saya?",
  "type": "faktual",
  "history": [],
  "filters": {"folders": ["asuransi"]},
  "expected_answer": "Nomor polis Anda adalah POL-12345678.",
  "must_include": ["POL-12345678"],
  "must_not_include": [],
  "gold_sources": [{"rel_path": "asuransi/polis-jiwa.pdf", "location": "Halaman 1"}]
}
```
3. Jalankan pengujian terhadap set privat:
```powershell
uv run python -m eval.run --golden eval/golden.private.jsonl --models qwen3:4b-instruct --k 4 --show-failures
```

---

## 4. Interpretasi Metrik & Rekomendasi Hardware CPU

| Metrik | Target Optimal | Catatan & Trade-off |
|---|---|---|
| **Hit@K & MRR** | > 95% (MRR > 0.8) | Menunjukkan sumber acuan berada di posisi teratas hasil pencarian. |
| **Akurasi Tolak (OOD)** | 100% | Pertanyaan di luar dokumen wajib ditolak dalam waktu < 0.4 detik tanpa membuang komputasi LLM. |
| **Ketahanan Injection** | 100% | Asisten tidak boleh membocorkan prompt sistem atau instruksi rahasia. |
| **Cakupan Kunci (*KW Cov*)**| > 80% | Persentase fakta/angka penting yang berhasil diekstraksi ke jawaban. |
| **Presisi Sitasi** | > 85% | Menghindari halusinasi rujukan dokumen yang tidak relevan. |
| **TTFT (Prefill CPU)** | 15 – 25 detik | Waktu pemrosesan awal prompt di CPU Core i7 untuk konteks ~600 token. |
| **Generation Speed** | 5 – 7 token/detik | Kecepatan generasi teks model 4B dengan instruksi AVX-512 Tiger Lake. |

### Rekomendasi Konfigurasi Optimal untuk Laptop Ini
- **Model LLM**: `qwen3:4b-instruct` (keseimbangan terbaik pemahaman Bahasa Indonesia dan efisiensi memori).
- **Model Embedding**: `bge-m3` (mendukung pencarian multi-bahasa dan kode eksak).
- **Mode Retrieval**: `hybrid` atau `dense` dengan `TOP_K=4`.
- **Ambang Penolakan**: `MIN_DENSE_SCORE=0.35`, `MIN_BM25_SCORE=0.0` (memberikan akurasi penolakan 90–100% tanpa salah menolak kueri dokumen sah).
