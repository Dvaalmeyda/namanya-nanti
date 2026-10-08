# Rekomendasi Peningkatan dan Rencana Pengembangan

Berdasarkan hasil pengujian empiris, evaluasi kuantitatif, dan keterbatasan sistem pada versi 0.1.0, dokumen ini merinci daftar rekomendasi peningkatan teknis yang dapat diimplementasikan pada iterasi berikutnya.

---

## 1. Prioritas Tinggi

### 1.1 Evaluasi pada Dokumen Pribadi Skala Penuh
- **Kondisi Saat Ini**: Pengujian kuantitatif baru mencakup 20 pertanyaan atas 6 berkas dokumen dummy di `data/sample/`.
- **Rencana Tindakan**:
  - Buat berkas `eval/golden.private.jsonl` menggunakan dokumen pribadi nyata pengguna (polis asuransi, surat perjanjian, slip gaji, laporan mutasi).
  - Susun minimal 30–50 pertanyaan acuan yang mencakup variasi istilah sehari-hari, salah ketik (*typo*), singkatan, dan pertanyaan multi-halaman.
  - Jalankan `uv run python -m eval.run --golden eval/golden.private.jsonl` secara berkala untuk memantau performa tanpa mempublikasikan berkas tersebut ke repositori Git.

### 1.2 Penyesuaian Nilai Default Ambang Batas Gerbang Penolakan
- **Kondisi Saat Ini**: Nilai default konfigurasi adalah `MIN_DENSE_SCORE=0.35` dan `MIN_BM25_SCORE=0.0`.
- **Temuan Sweep**: Pengujian sweep menunjukkan bahwa pasangan `MIN_DENSE_SCORE=0.45` dan `MIN_BM25_SCORE=1.0` menghasilkan akurasi penolakan 100% pada pertanyaan di luar domain (OOD) tanpa salah menolak dokumen sah.
- **Rencana Tindakan**: Perbarui nilai default di `app/config.py` dan `.env.example` ke nilai optimal hasil kalibrasi tersebut setelah divalidasi pada koleksi dokumen yang lebih besar.

### 1.3 Pencatatan Metrik TTFT (*Time to First Token*) dari Ollama
- **Kondisi Saat Ini**: Nilai `ttft_ms` pada laporan pengujian non-streaming tercatat 0.0 ms.
- **Rencana Tindakan**:
  - Ambil nilai `prompt_eval_duration` (dalam nanodetik) dari respons JSON lengkap klien Ollama dan konversi ke milidetik (`duration_ns / 1e6`).
  - Untuk endpoint streaming, ukur waktu dari pengiriman prompt hingga token pertama diterima oleh generator SSE.

---

## 2. Prioritas Menengah

### 2.1 Integrasi Optical Character Recognition (OCR)
- **Kondisi Saat Ini**: Halaman PDF hasil pemindaian yang memuat kurang dari 50 karakter teks hanya ditandai dengan bendera `needs_ocr=True` tanpa diekstrak isinya.
- **Rencana Tindakan**:
  - Integrasikan backend OCR lokal yang tidak membebani memori, misalnya bindings Tesseract pada PyMuPDF (`fitz.open().get_page_pixmap().pdfocr_tobytes()`) atau pustaka `RapidOCR`.
  - Berikan opsi konfigurasi bahasa OCR (`eng+ind`) pada file `.env`.
  - Tambahkan penanda status pengindeksan OCR pada respons endpoint `/api/v1/documents`.

### 2.2 Penambahan Model Reranking Lokal (*Cross-Encoder*)
- **Kondisi Saat Ini**: Peringkat kandidat potongan dokumen ditentukan melalui Reciprocal Rank Fusion (RRF) antara dense similarity dan BM25 score.
- **Rencana Tindakan**:
  - Tambahkan model cross-encoder lokal ringan (misalnya `bge-reranker-base` atau `bge-reranker-small`).
  - Alur: Ambil 20 kandidat via RRF, kemudian gunakan model reranker untuk menilai pasangan (kueri, chunk) dan pilih Top-4 terbaik untuk dimasukkan ke prompt LLM.
  - Ini berpotensi meningkatkan ketepatan seleksi konteks pada dokumen hukum yang panjang dengan terminologi yang mirip.

### 2.3 Penulisan Ulang Kueri Bersyarat (*Conditional Query Rewriting*)
- **Kondisi Saat Ini**: Opsi `QUERY_REWRITE` dinonaktifkan secara default (`false`) karena pemanggilan LLM tambahan untuk query rewrite menambah latensi 10–15 detik di CPU.
- **Rencana Tindakan**:
  - Terapkan deteksi heuristik sederhana: periksa apakah teks kueri mengandung kata ganti rujukan atau anafora (seperti *"dia"*, *"tersebut"*, *"itu"*, *"biaya tadi"*, *"rumah yang mana"*).
  - Jalankan query rewrite hanya jika kueri mengandung indikasi rujukan dan riwayat percakapan tidak kosong. Jika kueri bersifat mandiri (*standalone*), lewati langkah query rewrite untuk menghemat waktu komputasi.

---

## 3. Prioritas Jangka Panjang

### 3.1 Manajemen Sesi Percakapan di Sisi Server
- **Kondisi Saat Ini**: Riwayat percakapan dikirimkan oleh klien pada setiap permintaan (`history`). Server tidak menyimpan status percakapan.
- **Rencana Tindakan**:
  - Tambahkan tabel `conversations` dan `messages` pada basis data SQLite lokal.
  - Sediakan endpoint manajemen sesi (`POST /api/v1/conversations`, `GET /api/v1/conversations/{id}/messages`).
  - Izinkan klien cukup mengirimkan `conversation_id` pada permintaan chat.

### 3.2 Antarmuka Pengguna Berbasis Web (*Web UI*)
- **Kondisi Saat Ini**: Pengguna berinteraksi melalui Swagger UI (`/docs`) atau baris perintah terminal.
- **Rencana Tindakan**:
  - Bangun antarmuka web satu halaman (Single Page Application) sederhana menggunakan HTML, CSS modern, dan JavaScript murni tanpa framework eksternal yang berat.
  - Hubungkan antarmuka ke endpoint `/api/v1/chat/stream` untuk menampilkan efek pengetikan jawaban secara langsung dan kartu rujukan dokumen yang dapat diklik.

### 3.3 Akselerasi Inferensi Perangkat Keras
- **Kondisi Saat Ini**: Inferensi berjalan murni di CPU (4 core / 8 thread) karena GPU laptop (NVIDIA GeForce MX450 2 GB) tidak mendukung kebutuhan VRAM Ollama.
- **Rencana Tindakan**:
  - Jika perangkat ditingkatkan dengan GPU terpisah yang memiliki minimal 6 GB hingga 8 GB VRAM, aktifkan kembali akselerasi CUDA pada Ollama untuk meningkatkan kecepatan generasi teks dari ~6 token/detik menjadi 25–40 token/detik.
  - Eksplorasi inferensi langsung menggunakan mesin `llama.cpp` dengan kuantisasi bobot 4-bit (Q4_K_M) untuk model 7B atau 8B.
