"""Komponen visualisasi transparansi alur kerja RAG 8 tahap per giliran percakapan."""

from typing import Any
import pandas as pd
import streamlit as st
from frontend.utils.formatters import format_badge, format_ms, format_speed


def render_workflow_trace(trace_data: dict[str, Any], key_suffix: str = "") -> None:
    """Merender panel lipat inspeksi detail 8 tahap alur kerja RAG."""
    with st.expander("Alur Proses Kerja & Log Eksekusi"):
        sources = trace_data.get("sources", [])
        timing = trace_data.get("timing", {})
        refused = trace_data.get("refused", False)
        refusal_reason = trace_data.get("refusal_reason")
        question = trace_data.get("question", "-")
        history = trace_data.get("history", [])

        # 1. Query Formulation
        st.markdown("**1. Formulasi Kueri & Augmentasi Riwayat**")
        augmented = bool(history)
        aug_label = "Riwayat Percakapan Disertakan" if augmented else "Kueri Mandiri (Tanpa Riwayat)"
        st.caption(f"Pertanyaan Asli: `{question}`")
        st.caption(f"Status Konteks: `{aug_label}` | Giliran Riwayat: `{len(history)}`")

        # 2. Dense Embedding
        st.markdown("**2. Komputasi Vektor Embedding Kueri**")
        embed_ms = timing.get("embed_ms", 0.0)
        st.caption(f"Model: `bge-m3` | Dimensi: `1024 (float32)` | Durasi Komputasi: `{format_ms(embed_ms)}`")

        # 3. Dual Search Execution
        st.markdown("**3. Eksekusi Pencarian Ganda (Dense + BM25)**")
        st.caption("Dense: Kemiripan Kosinus NumPy di Memori | Lexical: FTS5 SQLite BM25 | Kandidat Awal: `20`")

        # 4. Relevance Gate Evaluation
        st.markdown("**4. Evaluasi Gerbang Penolakan Relevansi**")
        max_dense = max([s.get("dense_score") or 0.0 for s in sources], default=0.0)
        max_bm25 = max([s.get("bm25_score") or 0.0 for s in sources], default=0.0)
        gate_passed = not refused or refusal_reason != "low_relevance"
        gate_status = format_badge("LOLOS" if gate_passed else "DITOLAK")

        st.caption(f"Skor Dense Tertinggi: `{max_dense:.4f}` (Ambang: `0.35`)")
        st.caption(f"Skor BM25 Tertinggi: `{max_bm25:.2f}` (Ambang: `0.0`)")
        st.caption(f"Keputusan Gerbang: **{gate_status}** ({'Lolos ke perankingan' if gate_passed else 'Ditolak instan tanpa LLM'})")

        if not gate_passed:
            st.warning("Pemrosesan dihentikan pada gerbang relevansi karena skor berada di bawah ambang batas.")
            return

        # 5. RRF & Candidates Table
        st.markdown("**5. Reciprocal Rank Fusion (RRF) & Deduplikasi Dokumen**")
        if sources:
            rows = []
            for idx, s in enumerate(sources, start=1):
                rows.append({
                    "Rank": idx,
                    "Dokumen": s.get("filename", "-"),
                    "Lokasi": s.get("location", "-"),
                    "Dense": f"{s.get('dense_score', 0.0):.4f}" if s.get("dense_score") is not None else "-",
                    "BM25": f"{s.get('bm25_score', 0.0):.2f}" if s.get("bm25_score") is not None else "-",
                    "RRF": f"{s.get('rrf_score', 0.0):.5f}",
                    "Status": format_badge("DIRUJUK" if s.get("cited") else "TIDAK DIRUJUK"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption("Batas Konteks Maksimum: `4000 karakter` | Parameter RRF k: `60`")

        # 6. Prompt Assembly
        st.markdown("**6. Penyusunan Prompt & Injeksi Konteks**")
        prompt_tokens = timing.get("prompt_tokens", 0)
        st.caption(f"Jumlah Potongan Terpilih: `{len(sources)}` | Estimasi Token Prompt: `{prompt_tokens}`")
        st.caption("Struktur Konteks: Format XML `<dokumen no='n' sumber='...'>` dengan pembatas isolasi.")

        # 7. LLM Inference
        st.markdown("**7. Inferensi Model Bahasa & Profil Latensi**")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.caption(f"Model: `qwen3:4b-instruct` | Mode: `Non-Thinking (think=False)`")
            st.caption(f"Waktu Prefill: `{format_ms(timing.get('prefill_ms', 0.0))}` | TTFT: `{format_ms(timing.get('ttft_ms', 0.0))}`")
        with col_m2:
            st.caption(f"Kecepatan: `{format_speed(timing.get('tokens_per_s', 0.0))}` | Total Waktu: `{format_ms(timing.get('total_ms', 0.0))}`")
            st.caption(f"Token Output: `{timing.get('completion_tokens', 0)}`")

        # 8. Post-processing & Sitasi
        st.markdown("**8. Pascapemrosesan Sitasi & Verifikasi Akhir**")
        cited_count = sum(1 for s in sources if s.get("cited"))
        st.caption(f"Sitasi Tervalidasi: `{cited_count}` dari `{len(sources)}` potongan konteks.")
        if refused and refusal_reason == "not_in_context":
            st.info("Status Akhir: Model menjawab bahwa informasi tidak ditemukan di dokumen yang dilampirkan.")
        else:
            st.caption("Status Akhir: Jawaban faktual terverifikasi dengan rujukan dokumen.")
