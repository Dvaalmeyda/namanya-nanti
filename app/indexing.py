"""Pipeline pengindeksan dokumen: chunking sadar struktur, embedding BGE-M3, dan sinkronisasi inkremental."""

import argparse
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable, Generator, Optional

import numpy as np
from tqdm import tqdm

from app.config import Settings, get_settings
from app.loaders import Block, compute_file_hash, format_location, load_file, scan_directory
from app.logging_setup import setup_logging
from app import ollama_client
import app.store as store

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Unit teks terkecil yang siap diindeks dan di-embed."""

    chunk_id: str
    doc_id: str
    idx: int
    page: Optional[int]
    page_end: Optional[int]
    sheet: Optional[str]
    section: Optional[str]
    kind: str
    location: str
    text: str
    embed_text: str
    embedding: Optional[np.ndarray] = None


@dataclass
class SyncReport:
    """Laporan ringkasan hasil sinkronisasi pengindeksan dokumen."""

    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0
    total_chunks: int = 0
    duration_s: float = 0.0
    chunks_per_sec: float = 0.0
    errors: list[str] = field(default_factory=list)


# ==============================================================================
# File Lock Concurrency
# ==============================================================================


def is_pid_running(pid: int) -> bool:
    """Memeriksa apakah proses dengan PID tertentu masih aktif di sistem Windows."""
    if pid <= 0:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    exit_code = ctypes.c_ulong()
    success = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel32.CloseHandle(handle)
    return bool(success and exit_code.value == STILL_ACTIVE)


@contextmanager
def indexing_lock(index_dir: Path) -> Generator[None, None, None]:
    """Manajer konteks untuk mencegah eksekusi ganda proses pengindeksan."""
    index_dir.mkdir(parents=True, exist_ok=True)
    lock_file = index_dir / ".indexing.lock"

    if lock_file.exists():
        try:
            old_pid = int(lock_file.read_text(encoding="utf-8").strip())
            if is_pid_running(old_pid):
                raise RuntimeError(
                    f"Proses pengindeksan lain sedang berjalan (PID: {old_pid}). "
                    "Tunggu hingga selesai atau matikan proses tersebut."
                )
            logger.warning(f"Menghapus stale lock dari PID yang sudah mati: {old_pid}")
            lock_file.unlink(missing_ok=True)
        except (ValueError, OSError) as exc:
            logger.warning(f"Mengabaikan lock file rusak: {exc}")
            lock_file.unlink(missing_ok=True)

    current_pid = os.getpid()
    lock_file.write_text(str(current_pid), encoding="utf-8")
    try:
        yield
    finally:
        try:
            if lock_file.exists():
                lock_file.unlink(missing_ok=True)
        except OSError:
            pass


# ==============================================================================
# Chunking Sadar Struktur
# ==============================================================================


def _format_chunk_location(
    rel_path: str,
    page: Optional[int],
    page_end: Optional[int],
    sheet: Optional[str],
    section: Optional[str],
) -> str:
    """Menghasilkan sitasi lokasi chunk yang presisi."""
    parts = [rel_path]
    if sheet:
        parts.append(f"sheet: {sheet}")
    if page is not None:
        if page_end is not None and page_end != page:
            parts.append(f"hal. {page}-{page_end}")
        else:
            parts.append(f"hal. {page}")
    if section and (not sheet or section != f"Sheet: {sheet}"):
        parts.append(section)
    return f"[{' | '.join(parts)}]"


def _chunk_table_block(
    block: Block,
    doc_id: str,
    start_idx: int,
    chunk_size: int,
    filename: str,
) -> list[Chunk]:
    """Memotong tabel panjang tanpa memotong baris dan mengulang baris header."""
    lines = block.text.strip().splitlines()
    if len(lines) <= 2:
        loc = format_location(block)
        embed_prefix = f"{filename} > {block.section}\n" if block.section else f"{filename}\n"
        return [
            Chunk(
                chunk_id=f"{doc_id}:{start_idx:04d}",
                doc_id=doc_id,
                idx=start_idx,
                page=block.page,
                page_end=block.page,
                sheet=block.sheet,
                section=block.section,
                kind="table",
                location=loc,
                text=block.text,
                embed_text=embed_prefix + block.text,
            )
        ]

    header_line = lines[0]
    sep_line = lines[1]
    data_lines = lines[2:]

    if len(block.text) <= chunk_size:
        loc = format_location(block)
        embed_prefix = f"{filename} > {block.section}\n" if block.section else f"{filename}\n"
        return [
            Chunk(
                chunk_id=f"{doc_id}:{start_idx:04d}",
                doc_id=doc_id,
                idx=start_idx,
                page=block.page,
                page_end=block.page,
                sheet=block.sheet,
                section=block.section,
                kind="table",
                location=loc,
                text=block.text,
                embed_text=embed_prefix + block.text,
            )
        ]

    chunks: list[Chunk] = []
    current_rows: list[str] = []
    current_len = len(header_line) + len(sep_line) + 2

    for r in data_lines:
        r_len = len(r) + 1
        if current_rows and (current_len + r_len > chunk_size):
            table_md = "\n".join([header_line, sep_line] + current_rows)
            loc = format_location(block)
            embed_prefix = f"{filename} > {block.section}\n" if block.section else f"{filename}\n"
            c_idx = start_idx + len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{c_idx:04d}",
                    doc_id=doc_id,
                    idx=c_idx,
                    page=block.page,
                    page_end=block.page,
                    sheet=block.sheet,
                    section=block.section,
                    kind="table",
                    location=loc,
                    text=table_md,
                    embed_text=embed_prefix + table_md,
                )
            )
            current_rows = [r]
            current_len = len(header_line) + len(sep_line) + 2 + r_len
        else:
            current_rows.append(r)
            current_len += r_len

    if current_rows:
        table_md = "\n".join([header_line, sep_line] + current_rows)
        loc = format_location(block)
        embed_prefix = f"{filename} > {block.section}\n" if block.section else f"{filename}\n"
        c_idx = start_idx + len(chunks)
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}:{c_idx:04d}",
                doc_id=doc_id,
                idx=c_idx,
                page=block.page,
                page_end=block.page,
                sheet=block.sheet,
                section=block.section,
                kind="table",
                location=loc,
                text=table_md,
                embed_text=embed_prefix + table_md,
            )
        )

    return chunks


def chunk_blocks(
    blocks: list[Block],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[Chunk]:
    """Mengelompokkan blok-blok dokumen menjadi unit chunk dengan preservasi struktur."""
    if not blocks:
        return []

    doc_id = hashlib.sha1(blocks[0].rel_path.encode("utf-8")).hexdigest()[:16]
    filename = blocks[0].filename
    rel_path = blocks[0].rel_path

    chunks: list[Chunk] = []

    # Akumulator untuk teks non-tabel
    buf_texts: list[str] = []
    buf_page_start: Optional[int] = None
    buf_page_end: Optional[int] = None
    buf_sheet: Optional[str] = None
    buf_section: Optional[str] = None

    def flush_text_buffer() -> None:
        nonlocal buf_texts, buf_page_start, buf_page_end, buf_sheet, buf_section
        if not buf_texts:
            return

        combined_text = "\n\n".join(buf_texts).strip()
        buf_texts = []
        if not combined_text:
            return

        # Jika combined_text melebihi chunk_size, potong bertahap dengan overlap
        pos = 0
        total_len = len(combined_text)

        while pos < total_len:
            end_pos = min(pos + chunk_size, total_len)
            if end_pos < total_len:
                # Cari batas jeda kata/kalimat terdekat
                space_idx = combined_text.rfind(" ", pos + chunk_size // 2, end_pos)
                if space_idx != -1:
                    end_pos = space_idx

            slice_text = combined_text[pos:end_pos].strip()
            if slice_text:
                c_idx = len(chunks)
                loc = _format_chunk_location(
                    rel_path, buf_page_start, buf_page_end, buf_sheet, buf_section
                )
                embed_prefix = f"{filename} > {buf_section}\n" if buf_section else f"{filename}\n"
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_id}:{c_idx:04d}",
                        doc_id=doc_id,
                        idx=c_idx,
                        page=buf_page_start,
                        page_end=buf_page_end,
                        sheet=buf_sheet,
                        section=buf_section,
                        kind="paragraph",
                        location=loc,
                        text=slice_text,
                        embed_text=embed_prefix + slice_text,
                    )
                )

            if end_pos >= total_len:
                break
            pos = max(pos + 1, end_pos - chunk_overlap)

        buf_page_start = None
        buf_page_end = None
        buf_sheet = None
        buf_section = None

    for b in blocks:
        if b.kind == "table":
            flush_text_buffer()
            table_chunks = _chunk_table_block(b, doc_id, len(chunks), chunk_size, filename)
            chunks.extend(table_chunks)
            continue

        # Pergantian section atau sheet menandakan batas chunk baru
        section_changed = (buf_section is not None and b.section != buf_section)
        sheet_changed = (buf_sheet is not None and b.sheet != buf_sheet)
        if section_changed or sheet_changed:
            flush_text_buffer()

        # Inisialisasi metadata buffer jika kosong
        if not buf_texts:
            buf_page_start = b.page
            buf_page_end = b.page
            buf_sheet = b.sheet
            buf_section = b.section
        else:
            if b.page is not None:
                buf_page_end = b.page

        buf_texts.append(b.text)
        current_len = sum(len(t) for t in buf_texts) + len(buf_texts) * 2
        if current_len >= chunk_size:
            flush_text_buffer()

    flush_text_buffer()
    return chunks


# ==============================================================================
# Embedding & Reuse
# ==============================================================================


def embed_chunks(
    chunks: list[Chunk],
    doc_metadata: dict[str, Any],
    conn: Any,
    settings: Settings,
    show_progress: bool = True,
    embed_fn: Optional[Callable[[list[str], str], list[list[float]]]] = None,
) -> None:
    """Menghitung embedding atau memakai ulang embedding yang sudah ada di database."""
    if not chunks:
        return

    # 1. Optimasi Reuse Embedding: cek kesamaan (file_hash, filename)
    target_hash = doc_metadata["file_hash"]
    target_name = doc_metadata["filename"]
    existing_docs = store.get_documents_by_hash(conn, target_hash)

    for ex in existing_docs:
        if ex["filename"] == target_name and ex["doc_id"] != doc_metadata["doc_id"]:
            cached_chunks = store.get_chunks_by_doc_id(conn, ex["doc_id"])
            if len(cached_chunks) == len(chunks):
                # Salin seluruh vektor tanpa memanggil Ollama API
                logger.info(
                    f"Memakai ulang embedding dari dokumen donor '{ex['rel_path']}' "
                    f"untuk '{doc_metadata['rel_path']}'"
                )
                for ch, c_cached in zip(chunks, cached_chunks):
                    raw_blob = c_cached["embedding"]
                    ch.embedding = np.frombuffer(raw_blob, dtype=np.float32)
                return

    # 2. Hitung embedding baru via Ollama Client
    texts_to_embed = [ch.embed_text for ch in chunks]
    batch_size = max(1, settings.EMBED_BATCH)

    all_vectors: list[list[float]] = []
    n_batches = (len(texts_to_embed) + batch_size - 1) // batch_size
    disable_pbar = not show_progress or n_batches <= 1

    pbar = tqdm(
        total=len(texts_to_embed),
        desc=f"Embedding {doc_metadata['filename']}",
        unit="chunk",
        disable=disable_pbar,
    )

    try:
        for i in range(0, len(texts_to_embed), batch_size):
            batch = texts_to_embed[i : i + batch_size]
            if embed_fn is not None:
                vectors = embed_fn(batch, "doc")
            else:
                vectors = ollama_client.embed(batch, kind="doc")
            all_vectors.extend(vectors)
            pbar.update(len(batch))
    finally:
        pbar.close()

    for ch, vec in zip(chunks, all_vectors):
        ch.embedding = np.array(vec, dtype=np.float32)


# ==============================================================================
# Sinkronisasi Inkremental (Sync)
# ==============================================================================


def sync(
    root_dir: Optional[Path] = None,
    settings: Optional[Settings] = None,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
    embed_fn: Optional[Callable[[list[str], str], list[list[float]]]] = None,
) -> SyncReport:
    """Melakukan sinkronisasi dokumen disk dengan basis data index SQLite."""
    start_time = time.time()
    if settings is None:
        settings = get_settings()

    root = Path(root_dir) if root_dir is not None else settings.DOCS_DIR
    db_path = settings.INDEX_DIR / "index.db"
    conn = store.init_db(db_path)

    report = SyncReport()

    with indexing_lock(settings.INDEX_DIR):
        # Validasi konsistensi konfigurasi
        saved_model = store.get_setting(conn, "embed_model")
        if saved_model and saved_model != settings.EMBED_MODEL:
            raise ValueError(
                f"Model embedding di basis data ({saved_model}) berbeda dengan konfigurasi ({settings.EMBED_MODEL}). "
                "Jalankan 'rebuild' untuk mengindeks ulang basis data."
            )

        scanned_files = scan_directory(root, max_file_mb=settings.MAX_FILE_MB)
        existing_docs = {d["rel_path"]: d for d in store.get_all_documents(conn)}
        scanned_rel_set: set[str] = set()

        # 1. Hapus dokumen yang sudah tidak ada di disk
        for file_path in scanned_files:
            try:
                rel = str(file_path.relative_to(root).as_posix())
                scanned_rel_set.add(rel)
            except ValueError:
                scanned_rel_set.add(file_path.name)

        for rel_path, doc_info in list(existing_docs.items()):
            if rel_path not in scanned_rel_set:
                logger.info(f"Menghapus dokumen yang telah dihapus di disk: {rel_path}")
                store.delete_document(conn, doc_info["doc_id"])
                report.deleted += 1
                del existing_docs[rel_path]

        # 2. Proses file di disk
        total_files = len(scanned_files)
        for idx_file, file_path in enumerate(scanned_files, start=1):
            try:
                rel_path = str(file_path.relative_to(root).as_posix())
            except ValueError:
                rel_path = file_path.name

            if progress_cb:
                progress_cb(rel_path, idx_file, total_files)

            stat = file_path.stat()
            doc_rec = existing_docs.get(rel_path)

            # Jalur Cepat (Fast-path): jika size dan mtime identik
            if doc_rec is not None:
                size_match = stat.st_size == doc_rec["size"]
                mtime_match = abs(stat.st_mtime - doc_rec["mtime"]) < 0.001
                if size_match and mtime_match:
                    report.skipped += 1
                    continue

                curr_hash = compute_file_hash(file_path)
                if curr_hash == doc_rec["file_hash"]:
                    with conn:
                        conn.execute(
                            "UPDATE documents SET size = ?, mtime = ? WHERE doc_id = ?;",
                            (stat.st_size, stat.st_mtime, doc_rec["doc_id"]),
                        )
                    report.skipped += 1
                    continue

            # File baru atau konten berubah
            try:
                curr_hash = compute_file_hash(file_path)
                blocks = load_file(file_path, root_dir=root, settings=settings)
                if not blocks and stat.st_size > 0:
                    report.failed += 1
                    report.errors.append(f"Gagal mengekstrak konten: {rel_path}")
                    continue

                chunks = chunk_blocks(blocks, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)

                folder = ""
                if "/" in rel_path:
                    folder = rel_path.rsplit("/", 1)[0]

                doc_id = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:16]
                doc_metadata = {
                    "doc_id": doc_id,
                    "rel_path": rel_path,
                    "filename": file_path.name,
                    "file_type": file_path.suffix.lstrip(".").lower(),
                    "folder": folder,
                    "file_hash": curr_hash,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "needs_ocr": any(b.needs_ocr for b in blocks),
                    "indexed_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }

                # Embedding dihitung SEBELUM membuka transaksi tulis basis data
                embed_chunks(chunks, doc_metadata, conn, settings, embed_fn=embed_fn)

                # Simpan secara atomik
                store.save_document_and_chunks(conn, doc_metadata, chunks)

                if doc_rec is not None:
                    report.updated += 1
                else:
                    report.added += 1

                report.total_chunks += len(chunks)

            except Exception as exc:
                report.failed += 1
                err_msg = f"Gagal mengindeks {rel_path}: {exc}"
                report.errors.append(err_msg)
                logger.error(err_msg)

        # Simpan pengaturan aktif
        with conn:
            store.set_setting(conn, "embed_model", settings.EMBED_MODEL)
            store.set_setting(conn, "chunk_size", str(settings.CHUNK_SIZE))
            store.set_setting(conn, "chunk_overlap", str(settings.CHUNK_OVERLAP))
            store.set_setting(conn, "stemmer", settings.STEMMER)

    elapsed = time.time() - start_time
    report.duration_s = elapsed
    report.chunks_per_sec = report.total_chunks / max(elapsed, 0.001)
    conn.close()

    return report


# ==============================================================================
# CLI Entrypoint
# ==============================================================================


def main() -> None:
    """Antarmuka baris perintah pengindeksan dokumen."""
    parser = argparse.ArgumentParser(description="CLI Pengindeksan Dokumen Lokal.")
    parser.add_argument("command", choices=["build", "update", "rebuild", "status", "search"])
    parser.add_argument("query", nargs="?", default="", help="Kueri untuk perintah search")
    parser.add_argument("--root", type=str, default=None, help="Direktori dokumen (default: DOCS_DIR)")
    parser.add_argument("--folder", type=str, default=None, help="Filter folder dokumen")
    parser.add_argument("--k", type=int, default=5, help="Jumlah hasil pencarian (default: 5)")

    args = parser.parse_args()
    setup_logging()
    settings = get_settings()

    target_root = Path(args.root) if args.root else settings.DOCS_DIR
    db_path = settings.INDEX_DIR / "index.db"

    if args.command in ("build", "update"):
        print("=" * 70)
        print(f"MEMULAI SINKRONISASI PENGINDEKSAN: {target_root.resolve()}")
        print("=" * 70)
        rep = sync(root_dir=target_root, settings=settings)
        print("\nHASIL SINKRONISASI:")
        print(f"- Baru ditambahkan : {rep.added}")
        print(f"- Diperbarui       : {rep.updated}")
        print(f"- Dihapus          : {rep.deleted}")
        print(f"- Dilewati (sama)  : {rep.skipped}")
        print(f"- Gagal            : {rep.failed}")
        print(f"- Total chunk baru : {rep.total_chunks}")
        print(f"- Durasi proses    : {rep.duration_s:.2f} detik")
        print(f"- Kecepatan        : {rep.chunks_per_sec:.1f} chunk/detik")
        if rep.errors:
            print("\nDaftar Kesalahan:")
            for e in rep.errors:
                print(f"  * {e}")

    elif args.command == "rebuild":
        print("=" * 70)
        print(f"MEMBANGUN ULANG INDEKS DARI AWAL: {target_root.resolve()}")
        print("=" * 70)
        if db_path.exists():
            conn = store.get_connection(db_path)
            with conn:
                conn.execute("DELETE FROM chunks_fts;")
                conn.execute("DELETE FROM chunks;")
                conn.execute("DELETE FROM documents;")
                store.set_setting(conn, "index_version", "0")
            conn.close()
        rep = sync(root_dir=target_root, settings=settings)
        print(f"\nRebuild selesai: {rep.total_chunks} chunk diindeks dalam {rep.duration_s:.2f} detik.")

    elif args.command == "status":
        print("=" * 70)
        print(f"STATUS INDEKS BASIS DATA: {db_path.resolve()}")
        print("=" * 70)
        if not db_path.exists():
            print("Basis data indeks belum dibuat. Jalankan perintah 'build' terlebih dahulu.")
            return

        conn = store.get_connection(db_path)
        docs = store.get_all_documents(conn)
        cur = conn.execute("SELECT count(*) AS total_chunks FROM chunks;")
        total_chunks = cur.fetchone()["total_chunks"]

        db_size_kb = db_path.stat().st_size / 1024
        # Perkiraan memori vektor: N * 1024 dimensi * 4 byte (float32)
        v_mem_kb = (total_chunks * 1024 * 4) / 1024

        model_name = store.get_setting(conn, "embed_model") or "-"
        ocr_docs = [d["rel_path"] for d in docs if d["needs_ocr"]]

        print(f"- Total dokumen     : {len(docs)}")
        print(f"- Total chunk       : {total_chunks}")
        print(f"- Ukuran basis data : {db_size_kb:.1f} KB")
        print(f"- Estimasi RAM RAM  : {v_mem_kb:.1f} KB")
        print(f"- Model embedding   : {model_name}")
        print(f"- Dokumen butuh OCR : {len(ocr_docs)}")
        for d in ocr_docs:
            print(f"  * {d}")
        conn.close()

    elif args.command == "search":
        if not args.query:
            print("Error: Harap berikan kueri pencarian.")
            return

        print("=" * 70)
        print(f"PENCARIAN UJI: '{args.query}' (k={args.k}, folder={args.folder})")
        print("=" * 70)

        conn = store.get_connection(db_path)

        # 1. BM25 Search
        bm25_res = store.bm25_search(conn, args.query, k=args.k, folder=args.folder)
        print("\n--- 1. HASIL BM25 (FTS5) ---")
        if not bm25_res:
            print("Tidak ada kecocokan BM25.")
        for rowid, score in bm25_res:
            ch = store.get_chunk_by_rowid(conn, rowid)
            if ch:
                short_text = ch["text"][:147] + "..." if len(ch["text"]) > 150 else ch["text"]
                print(f"[{score:7.3f}] {ch['location']}")
                print(f"         {short_text.replace(chr(10), ' ')}")

        # 2. Dense Vector Search
        vindex = store.VectorIndex(dtype=settings.VECTOR_DTYPE)
        vindex.load_from_db(conn)

        q_vec = ollama_client.embed([args.query], kind="query")[0]
        q_arr = np.array(q_vec, dtype=np.float32)
        dense_res = vindex.search(q_arr, k=args.k, folder=args.folder)

        print("\n--- 2. HASIL DENSE VECTOR (BGE-M3) ---")
        if not dense_res:
            print("Tidak ada kecocokan Dense Vector.")
        for rowid, score in dense_res:
            ch = store.get_chunk_by_rowid(conn, rowid)
            if ch:
                short_text = ch["text"][:147] + "..." if len(ch["text"]) > 150 else ch["text"]
                print(f"[{score:7.3f}] {ch['location']}")
                print(f"         {short_text.replace(chr(10), ' ')}")

        conn.close()


if __name__ == "__main__":
    main()
