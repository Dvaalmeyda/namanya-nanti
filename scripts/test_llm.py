"""Script pengujian inferensi LLM murni dan demonstrasi tanya-jawab berbasis konteks dokumen."""

import sys
import time
from pathlib import Path

# Pastikan workspace root ada di sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings
from app.logging_setup import setup_logging
from app import ollama_client
import app.store as store


def main() -> None:
    setup_logging()
    settings = get_settings()

    print("=" * 70)
    print("PENGUJIAN GENERASI LLM & PREVIEW TANYA-JAWAB DOKUMEN")
    print(f"Model       : {settings.LLM_MODEL}")
    print(f"Ollama Host : {settings.OLLAMA_HOST}")
    print(f"Maks Token  : {settings.NUM_PREDICT}")
    print(f"Suhu (Temp) : {settings.TEMPERATURE}")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # 1. Uji LLM Murni (Tanpa Dokumen)
    # --------------------------------------------------------------------------
    prompt_umum = "Jelaskan dalam 2 kalimat ringkas mengapa pencatatan keuangan pribadi penting."
    print("\n--- 1. Uji LLM Murni (Pertanyaan Umum) ---")
    print(f"Pertanyaan : {prompt_umum}\n")

    t0 = time.perf_counter()
    res1 = ollama_client.chat([{"role": "user", "content": prompt_umum}], stream=False)
    dur1 = time.perf_counter() - t0

    content1 = res1.get("content", "")
    eval_count1 = res1.get("eval_count", 0)
    eval_dur1 = res1.get("eval_duration", 0)
    tps1 = (eval_count1 / (eval_dur1 / 1e9)) if eval_dur1 > 0 else (eval_count1 / max(dur1, 0.001))

    print(f"Jawaban LLM:\n{content1.strip()}\n")
    print(f"[Metrik: {eval_count1} token | {dur1:.2f}s | {tps1:.1f} token/detik]")

    # --------------------------------------------------------------------------
    # 2. Uji LLM Terikat Konteks Dokumen (Simulasi RAG Awal: Servis Mobil)
    # --------------------------------------------------------------------------
    db_path = settings.INDEX_DIR / "index.db"
    if not db_path.exists():
        print("\nDatabase index belum ada. Jalankan 'python -m app.indexing build' terlebih dahulu.")
        return

    conn = store.get_connection(db_path)

    pertanyaan_dok1 = (
        "Kapan servis mobil 20.000 KM dilakukan dan apa saja rincian penggantian suku cadang beserta kodenya?"
    )
    # Ambil chunk relevan menggunakan pencarian BM25
    matches1 = store.bm25_search(conn, "servis 20000 KM penggantian suku cadang", k=1)
    if not matches1:
        matches1 = [(1, 1.0)]

    chunk_data1 = store.get_chunk_by_rowid(conn, matches1[0][0])
    context1 = chunk_data1["text"] if chunk_data1 else ""
    loc1 = chunk_data1["location"] if chunk_data1 else ""

    prompt_rag1 = f"""Anda adalah asisten pribadi AI. Jawablah pertanyaan pengguna HANYA berdasarkan konteks dokumen di bawah ini. Jangan mengarang informasi. Sebutkan sumber dokumennya.

KONTEKS DOKUMEN:
Sumber: {loc1}
{context1}

PERTANYAAN:
{pertanyaan_dok1}

JAWABAN:"""

    print("\n" + "=" * 70)
    print("--- 2. Uji Berbasis Konteks Dokumen (Kasus: Catatan Servis Kendaraan) ---")
    print(f"Pertanyaan : {pertanyaan_dok1}")
    print(f"Sumber     : {loc1}\n")

    t0 = time.perf_counter()
    res2 = ollama_client.chat([{"role": "user", "content": prompt_rag1}], stream=False)
    dur2 = time.perf_counter() - t0

    content2 = res2.get("content", "")
    eval_count2 = res2.get("eval_count", 0)
    eval_dur2 = res2.get("eval_duration", 0)
    tps2 = (eval_count2 / (eval_dur2 / 1e9)) if eval_dur2 > 0 else (eval_count2 / max(dur2, 0.001))

    print(f"Jawaban LLM:\n{content2.strip()}\n")
    print(f"[Metrik: {eval_count2} token | {dur2:.2f}s | {tps2:.1f} token/detik]")

    # --------------------------------------------------------------------------
    # 3. Uji LLM Terikat Konteks Dokumen (Kasus: Tabel Kontrak Sewa Rumah)
    # --------------------------------------------------------------------------
    pertanyaan_dok2 = "Berapa total biaya sewa rumah dan bagaimana jadwal pembagian termin pembayarannya?"
    matches2 = store.bm25_search(conn, "biaya sewa jadwal pembayaran termin tabel", k=2)
    contexts2_list = []
    for r_id, _ in matches2:
        c_item = store.get_chunk_by_rowid(conn, r_id)
        if c_item:
            contexts2_list.append(f"Sumber: {c_item['location']}\n{c_item['text']}")

    context2_combined = "\n\n".join(contexts2_list)

    prompt_rag2 = f"""Anda adalah asisten pribadi AI. Jawablah pertanyaan pengguna HANYA berdasarkan konteks dokumen di bawah ini.

KONTEKS DOKUMEN:
{context2_combined}

PERTANYAAN:
{pertanyaan_dok2}

JAWABAN:"""

    print("=" * 70)
    print("--- 3. Uji Berbasis Konteks Dokumen (Kasus: Kontrak Sewa & Tabel Termin) ---")
    print(f"Pertanyaan : {pertanyaan_dok2}\n")

    t0 = time.perf_counter()
    res3 = ollama_client.chat([{"role": "user", "content": prompt_rag2}], stream=False)
    dur3 = time.perf_counter() - t0

    content3 = res3.get("content", "")
    eval_count3 = res3.get("eval_count", 0)
    eval_dur3 = res3.get("eval_duration", 0)
    tps3 = (eval_count3 / (eval_dur3 / 1e9)) if eval_dur3 > 0 else (eval_count3 / max(dur3, 0.001))

    print(f"Jawaban LLM:\n{content3.strip()}\n")
    print(f"[Metrik: {eval_count3} token | {dur3:.2f}s | {tps3:.1f} token/detik]")

    conn.close()
    print("=" * 70)
    print("PENGUJIAN SELESAI")
    print("=" * 70)


if __name__ == "__main__":
    main()
