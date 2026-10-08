"""Tahap 1 Evaluasi: Sweep parameter retrieval murni (tanpa inferensi LLM).

Menjalankan eksplorasi grid parameter retrieval secara cepat dan teroptimasi:
membandingkan mode (hybrid vs dense vs bm25), nilai TOP_K (3 vs 4 vs 6),
dan ambang penolakan relevansi (MIN_DENSE_SCORE & MIN_BM25_SCORE).
Menggunakan caching vektor kueri dan shared connection agar selesai dalam hitungan detik.
"""

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

from app.config import Settings, get_settings
from app import ollama_client
from app.retrieval import Filters, retrieve
from app import store
from eval.metrics import (
    calculate_hit_at_k,
    calculate_mrr,
    calculate_recall_at_k,
    calculate_refusal_accuracy,
)

logger = logging.getLogger(__name__)


def load_golden_dataset(file_path: Path) -> list[dict[str, Any]]:
    """Memuat kumpulan pertanyaan acuan emas dari berkas JSONL."""
    if not file_path.exists():
        raise FileNotFoundError(f"Berkas golden set tidak ditemukan: {file_path}")

    dataset: list[dict[str, Any]] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                item = json.loads(line_str)
                dataset.append(item)
            except json.JSONDecodeError as exc:
                logger.warning("Gagal membaca baris %d: %s", line_num, exc)

    return dataset


def evaluate_retrieval_configuration(
    dataset: list[dict[str, Any]],
    mode: str,
    top_k: int,
    min_dense: float,
    min_bm25: float,
    base_settings: Settings,
    conn: sqlite3.Connection,
    vindex: store.VectorIndex,
    embed_fn: Callable[[list[str], str], list[list[float]]],
) -> dict[str, Any]:
    """Mengevaluasi satu kombinasi parameter retrieval pada seluruh dataset."""
    settings = base_settings.model_copy(
        update={
            "TOP_K": top_k,
            "MIN_DENSE_SCORE": min_dense,
            "MIN_BM25_SCORE": min_bm25,
        }
    )

    mrr_list: list[float] = []
    hit_list: list[float] = []
    recall_list: list[float] = []
    refusal_acc_list: list[float] = []
    latencies_ms: list[float] = []

    for item in dataset:
        q_text = item["question"]
        q_type = item["type"]
        history = item.get("history", [])
        gold_sources = item.get("gold_sources", [])

        query_input = q_text
        if history:
            past_user = [m["content"] for m in history if m.get("role") == "user"]
            if past_user:
                query_input = f"{q_text} {past_user[-1]}"

        filters_obj = None
        if item.get("filters"):
            filters_obj = Filters(
                folders=item["filters"].get("folders"),
                file_types=item["filters"].get("file_types"),
                doc_ids=item["filters"].get("doc_ids"),
            )

        t0 = time.perf_counter()
        ret_res = retrieve(
            query=query_input,
            filters=filters_obj,
            top_k=top_k,
            mode=mode,
            settings=settings,
            conn=conn,
            vindex=vindex,
            embed_fn=embed_fn,
        )
        dur_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(dur_ms)

        hits_dicts = [h.model_dump() for h in ret_res.hits]

        # 1. Akurasi Penolakan
        ref_acc = calculate_refusal_accuracy(ret_res.refused, q_type)
        refusal_acc_list.append(ref_acc)

        # 2. Metrik Retrieval
        if gold_sources and not ret_res.refused:
            hit = calculate_hit_at_k(hits_dicts, gold_sources, top_k)
            rec = calculate_recall_at_k(hits_dicts, gold_sources, top_k)
            mrr_val = calculate_mrr(hits_dicts, gold_sources)

            hit_list.append(hit)
            recall_list.append(rec)
            mrr_list.append(mrr_val)
        elif gold_sources and ret_res.refused:
            hit_list.append(0.0)
            recall_list.append(0.0)
            mrr_list.append(0.0)

    avg_mrr = sum(mrr_list) / max(len(mrr_list), 1)
    avg_hit = sum(hit_list) / max(len(hit_list), 1)
    avg_recall = sum(recall_list) / max(len(recall_list), 1)
    avg_refusal_acc = sum(refusal_acc_list) / max(len(refusal_acc_list), 1)
    avg_lat_ms = sum(latencies_ms) / max(len(latencies_ms), 1)

    return {
        "mode": mode,
        "top_k": top_k,
        "min_dense": min_dense,
        "min_bm25": min_bm25,
        "mrr": round(avg_mrr, 4),
        "hit_at_k": round(avg_hit, 4),
        "recall_at_k": round(avg_recall, 4),
        "refusal_accuracy": round(avg_refusal_acc, 4),
        "latency_ms": round(avg_lat_ms, 2),
    }


def run_sweep(golden_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    """Menjalankan grid sweep pada beberapa konfigurasi retrieval."""
    base_settings = get_settings()
    dataset = load_golden_dataset(golden_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("TAHAP 1: SWEEP PARAMETER RETRIEVAL MURNI (TANPA PEMANGGILAN LLM)")
    print("=" * 80)
    print(f"Golden Set File  : {golden_path.resolve()}")
    print(f"Jumlah Pertanyaan: {len(dataset)}")

    # 1. Pra-komputasi embedding seluruh kueri untuk menghemat waktu CPU
    print("Membuat cache embedding kueri...", end=" ", flush=True)
    t_emb_0 = time.perf_counter()
    unique_queries = []
    for item in dataset:
        q_text = item["question"]
        history = item.get("history", [])
        if history:
            past_user = [m["content"] for m in history if m.get("role") == "user"]
            if past_user:
                q_text = f"{q_text} {past_user[-1]}"
        unique_queries.append(q_text)

    # Batch embedding 20 kueri sekaligus
    query_vectors = ollama_client.embed(unique_queries, kind="query")
    cache: dict[str, list[float]] = dict(zip(unique_queries, query_vectors))
    dur_cache_ms = (time.perf_counter() - t_emb_0) * 1000.0
    print(f"Selesai dalam {dur_cache_ms:.1f}ms ({len(cache)} kueri)")

    def cached_embed_fn(texts: list[str], kind: str) -> list[list[float]]:
        return [cache.get(t, [0.0] * 1024) for t in texts]

    # 2. Buka koneksi DB dan muat VectorIndex sekali saja
    db_path = base_settings.INDEX_DIR / "index.db"
    conn = store.get_connection(db_path)
    vindex = store.VectorIndex(dtype=base_settings.VECTOR_DTYPE)
    vindex.load_from_db(conn)

    # 3. Ruang parameter sweep
    modes = ["hybrid", "dense", "bm25"]
    top_ks = [3, 4, 6]
    rejection_configs = [
        (0.35, 0.0),   # Default baseline
        (0.25, -1.0),  # Toleran
        (0.45, 1.0),   # Ketat
    ]

    results: list[dict[str, Any]] = []
    total_combinations = len(modes) * len(top_ks) * len(rejection_configs)
    combo_idx = 0

    print("Memulai sweep parameter (27 kombinasi)...")
    for mode in modes:
        for k in top_ks:
            for min_d, min_b in rejection_configs:
                combo_idx += 1
                res = evaluate_retrieval_configuration(
                    dataset, mode, k, min_d, min_b, base_settings, conn, vindex, cached_embed_fn
                )
                results.append(res)
                print(
                    f"[{combo_idx:02d}/{total_combinations}] mode={mode:<6} | k={k} | "
                    f"min_dense={min_d:<4} | min_bm25={min_b:<4} -> "
                    f"Hit@K: {res['hit_at_k']*100:5.1f}% | MRR: {res['mrr']:.4f} | "
                    f"Tolak: {res['refusal_accuracy']*100:5.1f}% | Latensi: {res['latency_ms']:.2f}ms"
                )

    conn.close()

    # Urutkan berdasarkan MRR tertinggi, lalu Hit@K, lalu refusal accuracy, lalu latensi tercepat
    results.sort(key=lambda r: (r["mrr"], r["hit_at_k"], r["refusal_accuracy"], -r["latency_ms"]), reverse=True)

    # Simpan laporan
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_file = output_dir / f"sweep_retrieval_{timestamp}.md"
    csv_file = output_dir / f"sweep_retrieval_{timestamp}.csv"

    # 1. Tulis CSV
    with open(csv_file, "w", encoding="utf-8") as f:
        headers = ["mode", "top_k", "min_dense", "min_bm25", "mrr", "hit_at_k", "recall_at_k", "refusal_accuracy", "latency_ms"]
        f.write(",".join(headers) + "\n")
        for r in results:
            f.write(f"{r['mode']},{r['top_k']},{r['min_dense']},{r['min_bm25']},{r['mrr']},{r['hit_at_k']},{r['recall_at_k']},{r['refusal_accuracy']},{r['latency_ms']}\n")

    # 2. Tulis Markdown
    lines = [
        "# Laporan Sweep Retrieval (Tahap 1)",
        f"- Waktu Pelaksanaan: {datetime.now().isoformat()}",
        f"- Sumber Pertanyaan: `{golden_path.name}` ({len(dataset)} kueri)",
        "",
        "## Tabel Peringkat Konfigurasi Retrieval Terbaik",
        "",
        "| Peringkat | Mode | TOP_K | Min Dense | Min BM25 | MRR | Hit@K | Recall@K | Akurasi Tolak | Latensi (ms) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for idx, r in enumerate(results, start=1):
        lines.append(
            f"| {idx} | {r['mode']} | {r['top_k']} | {r['min_dense']} | {r['min_bm25']} | "
            f"{r['mrr']:.4f} | {r['hit_at_k']:.4f} | {r['recall_at_k']:.4f} | {r['refusal_accuracy']:.4f} | {r['latency_ms']:.2f} |"
        )

    best = results[0]
    lines.extend([
        "",
        "## Rekomendasi Konfigurasi Retrieval",
        f"- **Mode Terbaik**: `{best['mode']}`",
        f"- **TOP_K Terbaik**: `{best['top_k']}`",
        f"- **Ambang Batas**: `MIN_DENSE_SCORE={best['min_dense']}`, `MIN_BM25_SCORE={best['min_bm25']}`",
        f"- **Skor**: Hit@K = `{best['hit_at_k']*100:.1f}%`, MRR = `{best['mrr']:.4f}`, Rata-rata Latensi = `{best['latency_ms']:.2f} ms`",
    ])

    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n" + "=" * 80)
    print("HASIL SWEEP TAHAP 1 (TOP 5 KONFIGURASI TERBAIK):")
    print("=" * 80)
    print(f"{'Rank':<5} {'Mode':<8} {'K':<4} {'DenseThresh':<12} {'BM25Thresh':<11} {'MRR':<8} {'Hit@K':<8} {'Tolak':<8} {'Latensi':<10}")
    print("-" * 80)
    for idx, r in enumerate(results[:5], start=1):
        print(f"{idx:<5} {r['mode']:<8} {r['top_k']:<4} {r['min_dense']:<12} {r['min_bm25']:<11} {r['mrr']:<8.4f} {r['hit_at_k']*100:<7.1f}% {r['refusal_accuracy']*100:<7.1f}% {r['latency_ms']:<8.2f}ms")

    print(f"\nLaporan tersimpan di:\n- {md_file.resolve()}\n- {csv_file.resolve()}\n")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep Evaluasi Retrieval Cepat (Fase 5)")
    parser.add_argument("--golden", type=str, default="eval/golden.sample.jsonl", help="Path berkas golden dataset")
    parser.add_argument("--output-dir", type=str, default="eval/reports", help="Path direktori output laporan")
    args = parser.parse_args()

    run_sweep(Path(args.golden), Path(args.output_dir))


if __name__ == "__main__":
    main()
