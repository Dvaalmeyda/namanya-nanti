"""CLI interaktif percakapan RAG dokumen pribadi dengan streaming teks dan profil performa."""

import argparse
import sys
from typing import Optional

from app.config import get_settings
from app.logging_setup import setup_logging
from app.rag import answer_stream
from app.retrieval import Filters


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat Interaktif Dokumen Pribadi (Fase 3 RAG).")
    parser.add_argument("--folder", type=str, default=None, help="Filter pencarian hanya pada folder tertentu")
    parser.add_argument("--debug", action="store_true", help="Tampilkan detail chunk terambil dan skor retrieval")
    args = parser.parse_args()

    setup_logging()
    settings = get_settings()

    filters = Filters(folders=[args.folder]) if args.folder else None

    print("=" * 70)
    print("ASISTEN DOKUMEN PRIBADI - SESI PERCAKAPAN LOKAL")
    print(f"Model       : {settings.LLM_MODEL}")
    print(f"Embedding   : {settings.EMBED_MODEL}")
    if args.folder:
        print(f"Filter      : folder '{args.folder}'")
    if args.debug:
        print("Mode Debug  : AKTIF (Menampilkan skor retrieval detail)")
    print("Ketik 'exit' atau 'keluar' untuk mengakhiri sesi.")
    print("=" * 70)

    history: list[dict[str, str]] = []

    while True:
        try:
            print()
            user_input = input("Anda: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "keluar", "q"):
                print("Sesi percakapan berakhir.")
                break

            print("\nAsisten: ", end="", flush=True)

            full_answer_parts: list[str] = []
            final_sources: list[dict] = []
            final_timing: dict = {}
            is_refused: bool = False
            refusal_reason: Optional[str] = None

            # Eksekusi streaming
            stream_gen = answer_stream(
                question=user_input,
                history=history,
                filters=filters,
                mode="hybrid",
                settings=settings,
            )

            for event in stream_gen:
                evt_type = event.get("event")
                if evt_type == "token":
                    chunk_token = event.get("content", "")
                    sys.stdout.write(chunk_token)
                    sys.stdout.flush()
                    full_answer_parts.append(chunk_token)

                elif evt_type == "sources":
                    final_sources = event.get("sources", [])

                elif evt_type == "done":
                    is_refused = event.get("refused", False)
                    refusal_reason = event.get("refusal_reason")
                    final_timing = event.get("timing", {})

            full_answer = "".join(full_answer_parts).strip()
            print()  # newline setelah selesai streaming

            # Tampilkan rincian sumber jika ada
            if final_sources and not is_refused:
                print("\n--- SUMBER DOKUMEN ---")
                for s in final_sources:
                    status = "[DIRUJUK]" if s["cited"] else "[TIDAK DIRUJUK]"
                    loc = s["location"]
                    dup_info = f" (juga ada di: {', '.join(s['also_in'])})" if s["also_in"] else ""
                    print(f"  [{s['n']}] {status} {loc}{dup_info}")
                    if args.debug:
                        print(f"      Skor RRF: {s['rrf_score']:.4f} | Dense: {s['dense_score']} | BM25: {s['bm25_score']}")

            # Tampilkan metrik timing
            if final_timing:
                t_emb = final_timing.get("embed_ms", 0)
                t_srch = final_timing.get("search_ms", 0)
                ttft = final_timing.get("ttft_ms", 0)
                t_tot = final_timing.get("total_ms", 0)
                tps = final_timing.get("tokens_per_s", 0)
                tok_out = final_timing.get("completion_tokens", 0)
                print(
                    f"\n[Metrik: Embed {t_emb:.0f}ms | Search {t_srch:.0f}ms | "
                    f"TTFT {ttft:.0f}ms | Total {t_tot/1000:.2f}s | "
                    f"{tok_out} token ({tps:.1f} tok/s)]"
                )

            # Simpan riwayat percakapan di memori (in-memory only)
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": full_answer})

        except (KeyboardInterrupt, EOFError):
            print("\nSesi percakapan dihentikan.")
            break


if __name__ == "__main__":
    main()
