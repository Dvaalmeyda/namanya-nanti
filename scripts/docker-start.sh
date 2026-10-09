#!/bin/bash
set -e

echo "====================================================================="
echo " Personal Document Assistant - Docker Launcher (Linux / macOS)"
echo "====================================================================="
echo ""

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] Docker tidak ditemukan di sistem."
    echo "Silakan pasang Docker terlebih dahulu: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker daemon belum berjalan. Silakan jalankan layanan Docker terlebih dahulu."
    exit 1
fi

echo "[1/3] Menjalankan layanan kontainer via Docker Compose..."
docker compose up -d

echo ""
echo "[2/3] Menunggu antarmuka web Streamlit siap..."
attempts=0
max_attempts=60

while ! curl -s -f http://localhost:8501 >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$max_attempts" ]; then
        echo ""
        echo "[INFO] Pengunduhan model sedang berlangsung di latar belakang."
        echo "Pantau proses: docker compose logs -f"
        break
    fi
    printf "."
    sleep 3
done

echo ""
echo "[3/3] Seluruh layanan siap digunakan."
echo "====================================================================="
echo " Antarmuka Web: http://localhost:8501"
echo " Dokumentasi API: http://localhost:8000/docs"
echo "====================================================================="

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://localhost:8501 >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
    open http://localhost:8501 >/dev/null 2>&1 || true
fi
