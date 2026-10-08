"""Skrip pengujian dan benchmark end-to-end API Fase 4 (FastAPI + Ollama Asli).

Menguji endpoint /health, /search, /chat (3 kueri sample), dan /chat/stream
untuk mengukur efektivitas warm-up dan latensi end-to-end.
"""

import json
import time
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import get_settings


def run_benchmark():
    settings = get_settings()
    print("=" * 70)
    print("PENGUJIAN & BENCHMARK REST API FASE 4 (FASTAPI + OLLAMA)")
    print("=" * 70)
    print(f"Host Config : {settings.API_HOST}:{settings.API_PORT}")
    print(f"LLM Model   : {settings.LLM_MODEL}")
    print(f"Embed Model : {settings.EMBED_MODEL}")
    print(f"Warmup Flag : {settings.WARMUP}")
    print("=" * 70)

    app = create_app()

    with TestClient(app) as client:
        # 1. Health check
        print("\n--- 1. UJI /api/v1/health ---")
        t0 = time.perf_counter()
        resp_health = client.get("/api/v1/health")
        dur_health = (time.perf_counter() - t0) * 1000
        print(f"Status Code   : {resp_health.status_code} ({dur_health:.1f}ms)")
        health_data = resp_health.json()
        print(f"Sistem Status : {health_data['status']}")
        print(f"Ollama Hidup  : {health_data['ollama_connected']}")
        print(f"Model Ollama  : {health_data['models_available']}")
        print(f"Jumlah Dokumen: {health_data['document_count']}")
        print(f"Jumlah Chunk  : {health_data['chunk_count']}")

        # 2. Uji Search
        print("\n--- 2. UJI /api/v1/search (Retrieval Only) ---")
        search_payload = {
            "query": "SP-FLT-9902",
            "mode": "hybrid",
            "top_k": 2,
        }
        t0 = time.perf_counter()
        resp_search = client.post("/api/v1/search", json=search_payload)
        dur_search = (time.perf_counter() - t0) * 1000
        print(f"Status Code   : {resp_search.status_code} ({dur_search:.1f}ms)")
        search_data = resp_search.json()
        print(f"Total Hits    : {search_data['total_hits']}")
        for h in search_data["hits"]:
            print(f"  * [{h['rank']}] {h['filename']} - {h['location']} (RRF: {h['rrf_score']})")

        # 3. Uji 3 Kueri Chat (End-to-End Latency)
        queries = [
            ("Q1 (Warm-up test)", "Berapa total biaya sewa rumah dan durasinya?"),
            ("Q2 (Kode eksak)", "Suku cadang apa yang diganti pada servis berkala 20.000 km mobil Honda HR-V?"),
            ("Q3 (Tabel finansial)", "Berapa target dana darurat dan saldo saat ini di anggaran rumah tangga?"),
        ]

        print("\n--- 3. UJI /api/v1/chat (3 Pertanyaan Sampel End-to-End) ---")
        for tag, q in queries:
            print(f"\n[{tag}]")
            print(f"Pertanyaan : {q}")

            payload = {
                "question": q,
                "top_k": 3,
                "include_chunks": False,
            }

            t0 = time.perf_counter()
            resp_chat = client.post("/api/v1/chat", json=payload)
            dur_total = time.perf_counter() - t0

            if resp_chat.status_code == 200:
                chat_data = resp_chat.json()
                print(f"Status Code: {resp_chat.status_code} (Total: {dur_total:.2f}s)")
                print(f"Refused    : {chat_data['refused']}")
                print(f"Jawaban    : {chat_data['answer']}")
                print(f"Sitasi     : {[s['filename'] + ' -> ' + s['location'] for s in chat_data['sources'] if s['cited']]}")
                timing = chat_data.get("timing", {})
                print(
                    f"Timing     : Embed {timing.get('embed_ms', 0)}ms | "
                    f"Search {timing.get('search_ms', 0)}ms | "
                    f"TTFT {timing.get('ttft_ms', 0)}ms | "
                    f"Total {timing.get('total_ms', 0)}ms | "
                    f"{timing.get('tokens_per_s', 0)} tok/s"
                )
            else:
                print(f"ERROR: {resp_chat.status_code} -> {resp_chat.text}")

        # 4. Uji Streaming SSE
        print("\n--- 4. UJI /api/v1/chat/stream (SSE Stream) ---")
        stream_payload = {
            "question": "Sebutkan nomor polisi mobil Honda HR-V",
            "top_k": 2,
        }
        t0 = time.perf_counter()
        resp_stream = client.post("/api/v1/chat/stream", json=stream_payload)
        dur_stream = time.perf_counter() - t0
        print(f"Status Code   : {resp_stream.status_code} ({dur_stream:.2f}s)")
        print("Kutipan Event SSE (300 karakter pertama):")
        print(resp_stream.text[:300] + "...")

    print("\n" + "=" * 70)
    print("BENCHMARK REST API FASE 4 SELESAI DENGAN SUKSES")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
