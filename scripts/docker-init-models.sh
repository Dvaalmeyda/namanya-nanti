#!/bin/sh
set -e

OLLAMA_SERVER="${OLLAMA_HOST:-http://ollama:11434}"

echo "Menunggu server Ollama di $OLLAMA_SERVER siap..."
retry_count=0
max_retries=30

until ollama --host "$OLLAMA_SERVER" list > /dev/null 2>&1; do
    retry_count=$((retry_count + 1))
    if [ "$retry_count" -ge "$max_retries" ]; then
        echo "Error: Server Ollama tidak dapat dihubungi setelah $max_retries percobaan."
        exit 1
    fi
    echo "Server Ollama belum siap. Mencoba kembali dalam 2 detik ($retry_count/$max_retries)..."
    sleep 2
done

echo "Server Ollama siap."

pull_model_if_missing() {
    MODEL_NAME="$1"
    echo "Memeriksa model: $MODEL_NAME"
    if ollama --host "$OLLAMA_SERVER" list | grep -q "$MODEL_NAME"; then
        echo "Model $MODEL_NAME sudah tersedia. Melewati pengunduhan."
    else
        echo "Mengunduh model $MODEL_NAME dari Ollama registry..."
        ollama --host "$OLLAMA_SERVER" pull "$MODEL_NAME"
        echo "Model $MODEL_NAME berhasil diunduh."
    fi
}

pull_model_if_missing "bge-m3"
pull_model_if_missing "qwen3:4b-instruct"

echo "Seluruh model AI lokal siap digunakan."
