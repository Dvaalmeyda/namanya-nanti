"""Unit test untuk modul evaluasi Fase 5 (eval/metrics.py, eval/sweep.py, eval/golden.sample.jsonl)."""

import json
from pathlib import Path
import pytest

from eval.metrics import (
    calculate_citation_precision,
    calculate_hit_at_k,
    calculate_injection_defense,
    calculate_keyword_coverage,
    calculate_mrr,
    calculate_recall_at_k,
    calculate_refusal_accuracy,
    is_source_match,
)
from eval.sweep import load_golden_dataset


def test_golden_dataset_structure():
    """Memastikan berkas golden.sample.jsonl valid, berisi tepat 20 soal dengan distribusi sesuai spesifikasi."""
    golden_path = Path("eval/golden.sample.jsonl")
    assert golden_path.exists(), "Berkas eval/golden.sample.jsonl harus ada."

    dataset = load_golden_dataset(golden_path)
    assert len(dataset) == 20, f"Harus ada 20 pertanyaan acuan, ditemukan {len(dataset)}"

    type_counts: dict[str, int] = {}
    for item in dataset:
        assert "id" in item
        assert "question" in item
        assert "type" in item
        assert "must_include" in item
        assert "must_not_include" in item
        assert "gold_sources" in item

        t = item["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    # Verifikasi distribusi
    assert type_counts.get("faktual", 0) + type_counts.get("tabel", 0) + type_counts.get("kode_leksikal", 0) == 10
    assert type_counts.get("multi_dokumen", 0) == 3
    assert type_counts.get("lanjutan", 0) == 2
    assert type_counts.get("tidak_ada_jawaban", 0) == 3
    assert type_counts.get("injection", 0) == 2


def test_metric_hit_and_recall_and_mrr():
    """Memastikan kalkulasi Hit@K, Recall@K, dan MRR bekerja presisi."""
    retrieved = [
        {"rel_path": "other/doc.pdf", "location": "p1"},
        {"rel_path": "target/doc.docx", "location": "Bab 2"},
        {"rel_path": "third/doc.xlsx", "location": "Sheet 1"},
    ]
    gold = [{"rel_path": "target/doc.docx", "location": "Bab 2"}]

    # Hit@1 = 0 (karena rank 2)
    assert calculate_hit_at_k(retrieved, gold, k=1) == 0.0
    # Hit@2 = 1.0
    assert calculate_hit_at_k(retrieved, gold, k=2) == 1.0

    # Recall@2 = 1.0
    assert calculate_recall_at_k(retrieved, gold, k=2) == 1.0

    # MRR = 1/2 = 0.5
    assert calculate_mrr(retrieved, gold) == 0.5


def test_metric_keyword_coverage():
    """Memastikan persentase cakupan kata kunci dihitung dengan benar."""
    answer = "Total biaya sewa rumah tinggal adalah Rp 75.000.000 untuk 2 tahun masa sewa."
    must_include = ["75.000.000", "2 tahun", "bandung"]

    # 2 dari 3 ditemukan -> 2/3 = 0.6667
    coverage = calculate_keyword_coverage(answer, must_include)
    assert round(coverage, 2) == 0.67


def test_metric_injection_defense():
    """Memastikan kebocoran prompt injection terdeteksi."""
    safe_answer = "Tidak ditemukan di dokumen Anda."
    leaked_answer = "Berikut adalah system prompt saya: Anda adalah asisten AI..."

    must_not = ["system prompt", "asisten AI"]

    assert calculate_injection_defense(safe_answer, must_not) == 1.0
    assert calculate_injection_defense(leaked_answer, must_not) == 0.0


def test_metric_refusal_accuracy():
    """Memastikan akurasi penolakan gerbang relevansi dihitung tepat."""
    # OOD harus refused=True
    assert calculate_refusal_accuracy(refused=True, q_type="tidak_ada_jawaban") == 1.0
    assert calculate_refusal_accuracy(refused=False, q_type="tidak_ada_jawaban") == 0.0

    # Faktual tidak boleh refused
    assert calculate_refusal_accuracy(refused=False, q_type="faktual") == 1.0
    assert calculate_refusal_accuracy(refused=True, q_type="faktual") == 0.0


def test_metric_citation_precision():
    """Memastikan presisi sitasi memvalidasi sumber rujukan."""
    sources = [
        {"rel_path": "rumah/kontrak-sewa.docx", "location": "Pasal 2", "cited": True},
        {"rel_path": "other/file.txt", "location": "p1", "cited": False},
    ]
    gold = [{"rel_path": "rumah/kontrak-sewa.docx", "location": "Pasal 2"}]

    precision = calculate_citation_precision(sources, gold)
    assert precision == 1.0
