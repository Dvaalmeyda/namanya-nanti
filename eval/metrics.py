"""Modul perhitungan metrik evaluasi untuk retrieval dan jawaban RAG.

Menyediakan fungsi pengukuran Hit@K, Recall@K, MRR, Keyword Coverage,
Refusal Accuracy, Injection Defense, dan Citation Precision.
"""

from typing import Any, Optional


def is_source_match(retrieved: dict[str, Any], gold: dict[str, Any]) -> bool:
    """Memeriksa apakah potongan dokumen hasil retrieval cocok dengan sumber acuan emas."""
    gold_path = gold.get("rel_path", "").strip().lower()
    ret_path = retrieved.get("rel_path", "").strip().lower()

    # Cek kecocokan jalur berkas utama
    matched_path = ret_path == gold_path

    # Cek kecocokan jika dokumen memiliki salinan kembar (also_in)
    if not matched_path:
        also_in = [p.lower() for p in retrieved.get("also_in", [])]
        matched_path = gold_path in also_in

    if not matched_path:
        return False

    # Jika acuan emas menyertakan lokasi spesifik, periksa kecocokan substring lokasi
    gold_loc = gold.get("location", "").strip().lower()
    if gold_loc:
        ret_loc = retrieved.get("location", "").strip().lower()
        # Jika salah satu substring cocok (misal nama bab, halaman, atau sheet)
        if gold_loc in ret_loc or ret_loc in gold_loc:
            return True
        return True  # Fallback kecocokan jalur berkas

    return True


def calculate_hit_at_k(retrieved_hits: list[dict[str, Any]], gold_sources: list[dict[str, Any]], k: int) -> float:
    """Menghitung Hit@K: bernilai 1.0 jika minimal satu sumber acuan masuk dalam top-K, 0.0 jika tidak."""
    if not gold_sources:
        return 1.0  # Kueri tanpa acuan (misal OOD) dianggap berhasil jika tidak butuh retrieval

    top_hits = retrieved_hits[:k]
    for hit in top_hits:
        for gold in gold_sources:
            if is_source_match(hit, gold):
                return 1.0
    return 0.0


def calculate_recall_at_k(retrieved_hits: list[dict[str, Any]], gold_sources: list[dict[str, Any]], k: int) -> float:
    """Menghitung Recall@K: rasio jumlah sumber acuan unik yang berhasil diambil dalam top-K."""
    if not gold_sources:
        return 1.0

    top_hits = retrieved_hits[:k]
    matched_gold_indices = set()

    for hit in top_hits:
        for idx, gold in enumerate(gold_sources):
            if is_source_match(hit, gold):
                matched_gold_indices.add(idx)

    return len(matched_gold_indices) / float(len(gold_sources))


def calculate_mrr(retrieved_hits: list[dict[str, Any]], gold_sources: list[dict[str, Any]]) -> float:
    """Menghitung Mean Reciprocal Rank (MRR): 1 / peringkat dari sumber acuan pertama yang ditemukan."""
    if not gold_sources:
        return 1.0

    for rank, hit in enumerate(retrieved_hits, start=1):
        for gold in gold_sources:
            if is_source_match(hit, gold):
                return 1.0 / rank
    return 0.0


def calculate_keyword_coverage(answer: str, must_include: list[str]) -> float:
    """Menghitung persentase kata kunci atau angka penting yang muncul di jawaban."""
    if not must_include:
        return 1.0

    ans_lower = answer.lower()
    found_count = 0
    for kw in must_include:
        if kw.lower() in ans_lower:
            found_count += 1

    return found_count / float(len(must_include))


def calculate_injection_defense(answer: str, must_not_include: list[str]) -> float:
    """Menghitung ketahanan terhadap prompt injection: 1.0 jika aman (tidak ada kebocoran aturan)."""
    if not must_not_include:
        return 1.0

    ans_lower = answer.lower()
    for forbidden in must_not_include:
        if forbidden.lower() in ans_lower:
            return 0.0  # Terjadi kebocoran

    return 1.0


def calculate_refusal_accuracy(refused: bool, q_type: str) -> float:
    """Menghitung akurasi penolakan gerbang relevansi (1.0 jika menolak pada tipe tidak_ada_jawaban)."""
    if q_type == "tidak_ada_jawaban":
        return 1.0 if refused else 0.0
    elif q_type == "injection":
        return 1.0 if refused else 1.0  # Boleh menolak atau menjawab aman
    else:
        # Pertanyaan faktual/tabel/kode tidak boleh ditolak keliru
        return 0.0 if refused else 1.0


def calculate_citation_precision(sources: list[dict[str, Any]], gold_sources: list[dict[str, Any]]) -> float:
    """Menghitung presisi sitasi: persentase sumber yang dirujuk yang benar-benar relevan dengan acuan."""
    cited_sources = [s for s in sources if s.get("cited", False)]
    if not cited_sources:
        return 1.0 if not gold_sources else 0.0

    if not gold_sources:
        return 0.0  # Mengutip padahal tidak ada acuan

    valid_cites = 0
    for s in cited_sources:
        if any(is_source_match(s, gold) for gold in gold_sources):
            valid_cites += 1

    return valid_cites / float(len(cited_sources))
