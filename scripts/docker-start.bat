@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo  Personal Document Assistant - Docker Launcher
echo =====================================================================
echo.

where docker >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker tidak ditemukan di sistem.
    echo Silakan unduh dan pasang Docker Desktop terlebih dahulu:
    echo https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [PERINGATAN] Docker daemon / Docker Desktop belum berjalan.
    echo Silakan buka aplikasi Docker Desktop dan tunggu hingga statusnya 'Engine running'.
    echo.
    echo Mencoba memeriksa kembali dalam 10 detik...
    timeout /t 10 /nobreak >nul
    docker info >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Docker Desktop masih belum aktif. Jalankan Docker Desktop lalu coba lagi.
        pause
        exit /b 1
    )
)

echo [1/3] Menjalankan layanan kontainer via Docker Compose...
docker compose up -d

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Terjadi kesalahan saat menjalankan docker compose up.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Menunggu inisialisasi antarmuka web Streamlit...
set /a attempts=0
set /a max_attempts=60

:wait_loop
set /a attempts+=1
curl -s -f http://localhost:8501 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    goto ready
)

if %attempts% geq %max_attempts% (
    echo.
    echo [INFO] Layanan membutuhkan waktu lebih lama untuk inisialisasi awal (pengunduhan model AI).
    echo Anda dapat memantau proses dengan perintah: docker compose logs -f
    echo Akses antarmuka: http://localhost:8501
    goto open_browser
)

<nul set /p=.
timeout /t 3 /nobreak >nul
goto wait_loop

:ready
echo.
echo [3/3] Seluruh layanan siap digunakan.

:open_browser
echo.
echo =====================================================================
echo  Antarmuka Web: http://localhost:8501
echo  Dokumentasi API: http://localhost:8000/docs
echo =====================================================================
echo.
start http://localhost:8501

endlocal
