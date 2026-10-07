# FASE 7 (OPSIONAL) - Agentic RAG dengan LangGraph

> Prasyarat: Fase 4 mencapai target dan Fase 6 selesai. Model 4B sering lemah dalam tool calling; gunakan `qwen3:8b` (lambat di laptop) atau model di server GPU untuk fase ini.

## KONTEKS PROYEK (selalu tempel di awal sesi)
- Proyek: asisten AI tanya-jawab atas dokumen internal perusahaan yang SANGAT RAHASIA. Semuanya berjalan lokal.
- Larangan mutlak: tidak ada panggilan ke layanan eksternal (API LLM cloud, telemetry, tracing cloud, CDN, font atau skrip eksternal). Hanya localhost.
- Lingkungan awal: laptop Windows 11 (PowerShell), CPU-only (i7-1165G7, RAM 16 GB; GPU MX450 2 GB tidak dipakai). Kelak dipindah ke server dengan GPU, jadi semua pengaturan lewat config/.env; tidak ada path atau nama model yang di-hardcode.
- Stack terkunci: Python 3.11+ dengan uv, Ollama (LLM `qwen3:4b-instruct`, embedding `bge-m3`), Qdrant mode lokal (tanpa server), SQLite FTS5 untuk BM25, FastAPI. Dokumen berbahasa Indonesia (sebagian Inggris).
- Data: dokumen asli TIDAK boleh masuk repo. Pengembangan dan tes hanya memakai dokumen dummy di `data/sample/`. Jangan pernah mencatat isi dokumen atau isi pertanyaan di log.
- Cara kerja: tulis rencana singkat dulu, lalu implementasi, tes, dan jalankan. Jangan menambah dependensi tanpa alasan tertulis. Jelaskan keputusan penting dalam 1-2 kalimat. Kerjakan HANYA fase ini; berhenti dan lapor setelah selesai.

## TUGAS
Tambahkan mode agent di `app/agent/` tanpa menggantikan pipeline Fase 3.

1. Graf LangGraph: klasifikasi pertanyaan, lalu salah satu dari (retrieve | pecah pertanyaan | minta klarifikasi), nilai kecukupan konteks, tulis ulang kueri (maksimal 2 kali), lalu jawab.
2. Tool read-only: `cari_dokumen(query, filter)`, `ambil_halaman(file, page)`, `bandingkan(file_a, file_b, topik)`. Semua tool melewati filter ACL yang sama dengan Fase 3.
3. Batas keras: maksimal 5 langkah, timeout per tool, dan fallback deterministik ke pipeline Fase 3 bila agent gagal atau melewati batas.
4. Tracing hanya lokal (JSONL; Langfuse self-hosted opsional). Jangan memakai LangSmith atau layanan cloud lain.
5. Perluas eval set dengan pertanyaan multi-langkah. Bandingkan agent dan RAG biasa pada akurasi dan latensi.
6. Uji keamanan: tool tidak boleh bisa menulis file, menjalankan shell, atau mengakses web. Tambahkan kasus injection yang menyasar pemanggilan tool.

## KRITERIA SELESAI
- Agent hanya dijadikan default bila mengungguli baseline Fase 3 dengan selisih yang jelas pada eval; laporkan angkanya apa adanya, termasuk bila agent tidak lebih baik.
