import argparse
import sys
import time
from pathlib import Path
from typing import Optional

# Pastikan root workspace terdaftar di sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings
from app.privacy import apply_offline_env, assert_local_only
from app import ollama_client


SAMPLE_SENTENCES = [
    "Asuransi kesehatan keluarga memberikan perlindungan finansial untuk rawat inap.",
    "Perjanjian sewa rumah tinggal mencakup ketentuan uang muka dan jadwal termin.",
    "Pengeluaran bulanan mencakup belanja dapur, utilitas listrik, dan tagihan air.",
    "Servis berkala mobil dilakukan pada interval kilometer tertentu di bengkel resmi.",
    "Suku cadang kampas rem depan diganti untuk memastikan keselamatan berkendara.",
    "Rencana keuangan masa depan memerlukan alokasi dana darurat yang memadai.",
    "Klaim asuransi dapat diproses secara non-tunai di jaringan rumah sakit rekanan.",
    "Pihak kedua wajib mematuhi aturan tata tertib lingkungan tempat tinggal.",
    "Pencatatan anggaran tahunan membantu mengevaluasi stabilitas keuangan keluarga.",
    "Filter oli dan cairan rem wajib diperiksa secara berkala oleh teknisi handal.",
    "Dokumen kontrak mengatur hak dan kewajiban masing-masing pihak secara tegas.",
    "Investasi reksadana dilakukan melalui mekanisme autodebet setiap tanggal tertentu.",
    "Pengecualian klaim berlaku untuk kondisi medis yang telah ada sebelum masa tunggu.",
    "Rumah sewa berlokasi strategis di kawasan pemukiman yang aman dan asri.",
    "Penggantian busi iridium meningkatkan efisiensi pembakaran mesin kendaraan.",
    "Manajemen keuangan yang disiplin mencegah beban utang yang berlebihan.",
]

PREFILL_BASE_TEXT = (
    "Dokumen ini memuat rangkuman rinci mengenai pedoman operasional asuransi, tata kelola kontrak sewa, "
    "dan pencatatan anggaran rumah tangga secara komprehensif. "
    "Setiap komponen diatur berdasarkan kesepakatan tertulis yang mengikat seluruh pihak. "
    "Pelaksanaan pemeliharaan berkala atas properti maupun kendaraan bermotor menjadi tanggung jawab pihak terkait. "
) * 18  # Sekitar 800 - 1000 token prompt


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Mencetak tabel ASCII rapi ke terminal."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    print(sep)
    header_str = "| " + " | ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers)) + " |"
    print(header_str)
    print(sep)
    for row in rows:
        row_str = "| " + " | ".join(f"{str(val):<{col_widths[i]}}" for i, val in enumerate(row)) + " |"
        print(row_str)
    print(sep)


def run_benchmark(
    llm_models: list[str],
    embed_model: str,
    thread_options: list[Optional[int]],
) -> None:
    settings = get_settings()
    apply_offline_env()
    assert_local_only(settings.OLLAMA_HOST)

    print("\n" + "=" * 70)
    print("PEMERIKSAAN LINGKUNGAN & BENCHMARK LOKAL (FASE 0)")
    print("=" * 70)
    print(f"Ollama Host : {settings.OLLAMA_HOST}")
    print(f"Allow Remote: {settings.ALLOW_REMOTE}")

    # 1. Cek koneksi & ketersediaan model
    try:
        available_models = ollama_client.list_models()
    except ollama_client.OllamaUnavailable as e:
        print(f"\n[ERROR] Koneksi gagal: {e}")
        return
    except Exception as e:
        print(f"\n[ERROR] Gagal menghubungi Ollama: {e}")
        return

    print(f"Model tersedia di Ollama ({len(available_models)}): {', '.join(available_models) if available_models else '(belum ada)'}")

    missing_models: list[str] = []
    if embed_model not in available_models and not any(m.startswith(f"{embed_model}:") for m in available_models):
        missing_models.append(embed_model)

    for m in llm_models:
        if m not in available_models and not any(avail.startswith(f"{m}:") for avail in available_models):
            missing_models.append(m)

    if missing_models:
        print("\n" + "!" * 70)
        print("PERINGATAN: Model yang dikonfigurasi belum terunduh di Ollama!")
        print("Model yang belum tersedia:", ", ".join(missing_models))
        print("\nJalankan perintah berikut di PowerShell untuk mengunduh:")
        for mm in missing_models:
            print(f"   ollama pull {mm}")
        print("!" * 70 + "\n")
        return

    # 2. Uji Embedding
    print(f"\n--- 1. Uji Model Embedding: {embed_model} ---")
    embed_rows: list[list[str]] = []

    # Run Dingin
    t0 = time.perf_counter()
    vecs_cold = ollama_client.embed(SAMPLE_SENTENCES, kind="doc")
    dur_cold = (time.perf_counter() - t0) * 1000
    dim = len(vecs_cold[0]) if vecs_cold else 0

    # Run Hangat
    t1 = time.perf_counter()
    vecs_warm = ollama_client.embed(SAMPLE_SENTENCES, kind="doc")
    dur_warm = (time.perf_counter() - t1) * 1000

    embed_rows.append(["16 Kalimat (Cold)", f"{dur_cold:.1f} ms", f"{dim} dimensi", f"{dur_cold / len(SAMPLE_SENTENCES):.1f} ms/kalimat"])
    embed_rows.append(["16 Kalimat (Warm)", f"{dur_warm:.1f} ms", f"{dim} dimensi", f"{dur_warm / len(SAMPLE_SENTENCES):.1f} ms/kalimat"])
    print_table(["Skenario Embed", "Total Waktu", "Dimensi Vektor", "Rata-rata Latensi"], embed_rows)

    # 3. Uji LLM per variasi model & thread
    print("\n--- 2. Uji Model LLM (Prefill & Generation Throughput) ---")
    llm_headers = ["Model", "Threads", "Prefill (tok/s)", "Generate (tok/s)", "Load Model (ms)", "Alokasi VRAM (GPU)"]
    llm_rows: list[list[str]] = []

    for model in llm_models:
        for th in thread_options:
            settings.LLM_MODEL = model
            settings.NUM_THREAD = th

            # Siapkan pesan uji
            messages = [
                {
                    "role": "user",
                    "content": f"Berdasarkan informasi berikut:\n{PREFILL_BASE_TEXT}\nSebutkan 3 poin utama dan buat ringkasan singkat dalam 150 kata.",
                }
            ]

            try:
                res = ollama_client.chat(messages, stream=False)
                assert isinstance(res, dict)

                p_count = res.get("prompt_eval_count", 0)
                p_dur_ns = res.get("prompt_eval_duration", 0)
                prefill_speed = (p_count / (p_dur_ns / 1e9)) if p_dur_ns > 0 else 0.0

                e_count = res.get("eval_count", 0)
                e_dur_ns = res.get("eval_duration", 0)
                gen_speed = (e_count / (e_dur_ns / 1e9)) if e_dur_ns > 0 else 0.0

                load_ms = res.get("load_duration", 0) / 1e6

                # Cek status memori di /api/ps
                ps_list = ollama_client.loaded_models()
                vram_info = "N/A"
                for ps_m in ps_list:
                    if model in ps_m["model"]:
                        size = ps_m.get("size", 0)
                        vram = ps_m.get("size_vram", 0)
                        if size > 0:
                            vram_info = f"{vram / size * 100:.1f}% ({vram // (1024**2)} MB)"
                        break

                th_str = str(th) if th is not None else "Auto"
                llm_rows.append([
                    model,
                    th_str,
                    f"{prefill_speed:.1f}",
                    f"{gen_speed:.1f}",
                    f"{load_ms:.1f}",
                    vram_info,
                ])
            except Exception as e:
                llm_rows.append([model, str(th), "ERROR", "ERROR", "-", str(e)[:30]])

    print_table(llm_headers, llm_rows)
    print("\nBenchmark selesai.")


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Pemeriksaan lingkungan dan benchmark lokal Ollama.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=[settings.LLM_MODEL],
        help="Daftar nama model LLM yang diuji.",
    )
    parser.add_argument(
        "--embed-model",
        default=settings.EMBED_MODEL,
        help="Model embedding yang diuji.",
    )
    parser.add_argument(
        "--num-thread",
        nargs="+",
        type=int,
        default=[4, 8],
        help="Daftar variasi jumlah thread CPU yang diuji (misal: 4 8).",
    )

    args = parser.parse_args()
    run_benchmark(
        llm_models=args.models,
        embed_model=args.embed_model,
        thread_options=args.num_thread,
    )


if __name__ == "__main__":
    main()
