# Personal Document Assistant (Lokal & Offline)

Asisten AI tanya-jawab atas dokumen pribadi (polis asuransi, kontrak sewa, anggaran keuangan, catatan servis kendaraan, dsb.) yang berjalan 100% lokal di komputer tanpa ketergantungan internet.

---

## 1. Prasyarat Sistem

1. **Python 3.11+** (disarankan Python 3.12 atau 3.13)
2. **uv** (paket manager Python modern dan cepat):
   ```powershell
   winget install astral-sh.uv
   ```
3. **Ollama**:
   Pastikan aplikasi Ollama terinstal dan service-nya aktif di latar belakang (`http://127.0.0.1:11434`).

### Konfigurasi Penting Server Ollama (Laptop GPU MX450 2 GB & CPU 16 GB RAM)
GPU NVIDIA GeForce MX450 (2 GB VRAM) tidak mendukung fitur 16-bit storage Vulkan yang dibutuhkan Ollama, sehingga menyebabkan error `llama-server process has terminated: exit status 0xe06d7363`.

Oleh karena itu, server Ollama wajib dijalankan dalam **mode CPU murni (AVX-512 Tiger Lake)**.
Jalankan perintah ini di PowerShell sekali untuk mendaftarkan variabel secara permanen di akun Windows Anda:
```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_VULKAN", "0", "User")
[Environment]::SetEnvironmentVariable("CUDA_VISIBLE_DEVICES", "-1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "2", "User")
```
Setelah itu, restart aplikasi Ollama dari Start Menu atau System Tray Windows.

Atau jika menjalankan Ollama via terminal PowerShell:
```powershell
$env:OLLAMA_VULKAN = "0"
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "2"
ollama serve
```

---

## 2. Langkah Setup Proyek

### a. Sinkronisasi Dependensi
Jalankan perintah berikut di root folder proyek:
```powershell
uv sync
```

### b. Konfigurasi Environment
Salin template konfigurasi:
```powershell
Copy-Item .env.example .env
```
Anda dapat menyesuaikan nama model atau path di dalam file `.env` jika diperlukan.

### c. Unduh Model di Ollama
Unduh model embedding dan model LLM baseline:
```powershell
ollama pull bge-m3
ollama pull qwen3:4b-instruct
```

---

## 3. Eksekusi Script Utilitas & Pengujian

### a. Membuat Dokumen Uji Dummy (Sample)
Menghasilkan 6 file dummy berbahasa Indonesia di folder `data/sample/`:
```powershell
uv run python scripts/make_sample_docs.py
```

### b. Memeriksa Lingkungan & Benchmark Kecepatan
Mengukur ketersediaan model, kecepatan prefill, kecepatan generate token/detik, alokasi VRAM GPU MX450, serta komparasi CPU thread:
```powershell
uv run python scripts/check_env.py
```

Opsi pengujian lanjutan:
```powershell
# Membandingkan thread 4 vs 8
uv run python scripts/check_env.py --num-thread 4 8

# Membandingkan beberapa model LLM (jika sudah di-pull)
uv run python scripts/check_env.py --models qwen3:4b-instruct qwen3.5:4b
```

### c. Menguji Mode CPU-Only (Membandingkan GPU vs CPU)
Untuk mengukur benchmark tanpa menggunakan GPU NVIDIA MX450:
1. Hentikan service Ollama di tray Windows.
2. Jalankan Ollama di PowerShell dengan flag CUDA dinonaktifkan:
   ```powershell
   $env:CUDA_VISIBLE_DEVICES = "-1"
   ollama serve
   ```
3. Di terminal PowerShell lain, jalankan kembali:
   ```powershell
   uv run python scripts/check_env.py
   ```

### d. Menjalankan Tes Unit (Keamanan Socket Terisolasi)
Pengujian otomatis menggunakan `pytest` dengan proteksi `pytest-socket` (koneksi luar diblokir, hanya loopback yang diizinkan):
```powershell
uv run pytest
```
