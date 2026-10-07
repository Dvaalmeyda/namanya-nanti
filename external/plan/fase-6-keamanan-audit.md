# FASE 6 - Keamanan dan audit

> Prasyarat: Fase 5 selesai.

## KONTEKS PROYEK (selalu tempel di awal sesi)
- Proyek: asisten AI tanya-jawab atas dokumen internal perusahaan yang SANGAT RAHASIA. Semuanya berjalan lokal.
- Larangan mutlak: tidak ada panggilan ke layanan eksternal (API LLM cloud, telemetry, tracing cloud, CDN, font atau skrip eksternal). Hanya localhost.
- Lingkungan awal: laptop Windows 11 (PowerShell), CPU-only (i7-1165G7, RAM 16 GB; GPU MX450 2 GB tidak dipakai). Kelak dipindah ke server dengan GPU, jadi semua pengaturan lewat config/.env; tidak ada path atau nama model yang di-hardcode.
- Stack terkunci: Python 3.11+ dengan uv, Ollama (LLM `qwen3:4b-instruct`, embedding `bge-m3`), Qdrant mode lokal (tanpa server), SQLite FTS5 untuk BM25, FastAPI. Dokumen berbahasa Indonesia (sebagian Inggris).
- Data: dokumen asli TIDAK boleh masuk repo. Pengembangan dan tes hanya memakai dokumen dummy di `data/sample/`. Jangan pernah mencatat isi dokumen atau isi pertanyaan di log.
- Cara kerja: tulis rencana singkat dulu, lalu implementasi, tes, dan jalankan. Jangan menambah dependensi tanpa alasan tertulis. Jelaskan keputusan penting dalam 1-2 kalimat. Kerjakan HANYA fase ini; berhenti dan lapor setelah selesai.

## TUGAS
Perketat keamanan dan tambahkan audit.

1. `docs/threat-model.md` (1-2 halaman): aset, aktor, dan ancaman: kebocoran lewat jaringan, prompt injection dari isi dokumen, bypass ACL, kebocoran lewat log, pencurian index atau disk, jawaban melampaui izin, penyalahgunaan endpoint admin. Untuk tiap ancaman: mitigasi dan di mana mitigasi itu ditegakkan dan diuji.
2. Guard jaringan: saat startup, `assert_local_only` untuk semua URL; self-check yang gagal bila ada host non-loopback tanpa `ALLOW_REMOTE=true`. Tes yang memastikan tidak ada soket keluar selain 127.0.0.1.
3. Audit log JSONL append-only (`data/audit/`): timestamp, user, role, hash pertanyaan (teks asli hanya jika `LOG_QUESTIONS=true`), chunk_id yang dikembalikan, refused, latensi. Rotasi harian, tanpa isi dokumen.
4. Uji prompt injection: dokumen "instruksi jahat" dari Fase 0 tidak boleh membuat asisten membocorkan prompt sistem, melanggar aturan sitasi, atau menampilkan dokumen di luar izin. Tambahkan minimal 8 kasus ke eval set dan jalankan lewat harness Fase 4.
5. Uji ACL menyeluruh: pengguna tanpa izin tidak pernah menerima teks chunk, nama file, maupun jumlah hasil dari dokumen terlarang (periksa juga pesan error dan output debug).
6. Higiene: pre-commit hook yang memblokir commit file di `data/private/`, `data/index/`, `.env`, `eval/*.private.*`; `pip-audit` untuk dependensi; masker PII (NIK, NPWP, nomor telepon, email) khusus untuk LOG.
7. `docs/security-checklist.md` untuk go-live di server: enkripsi disk (BitLocker/LUKS), akun layanan non-admin, firewall tanpa egress, backup terenkripsi, SSO, rotasi log, kebijakan retensi.

## KRITERIA SELESAI
- Semua tes hijau, termasuk injection dan ACL.
- Laporkan secara jujur kelemahan yang belum tertutup.
