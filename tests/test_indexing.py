"""Unit test komprehensif untuk app/store dan app/indexing (Fase 2: Indexing)."""

import hashlib
from pathlib import Path
import sqlite3
import pytest
import numpy as np

from app.config import get_settings
from app.loaders import Block
import app.store as store
import app.indexing as indexing


# ==============================================================================
# 1. Test Store: Schema, CRUD, & FTS
# ==============================================================================


def test_store_schema_and_crud(tmp_path: Path):
    """Memastikan inisialisasi skema basis data, operasi CRUD, dan cascade delete bekerja benar."""
    db_file = tmp_path / "test_store.db"
    conn = store.init_db(db_file)

    # Verifikasi PRAGMA
    cur = conn.execute("PRAGMA foreign_keys;")
    assert cur.fetchone()[0] == 1

    cur = conn.execute("PRAGMA journal_mode;")
    assert cur.fetchone()[0].lower() == "wal"

    # Simpan dokumen dan 2 chunk dummy
    doc_data = {
        "doc_id": "doc1234567890123",
        "rel_path": "finance/budget.xlsx",
        "filename": "budget.xlsx",
        "file_type": "xlsx",
        "folder": "finance",
        "file_hash": "hash12345",
        "size": 2048,
        "mtime": 1700000000.0,
        "needs_ocr": False,
        "indexed_at": "2025-01-01T12:00:00",
    }

    dummy_vec1 = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    dummy_vec2 = np.array([0.5, 0.6, 0.7, 0.8], dtype=np.float32)

    chunks = [
        indexing.Chunk(
            chunk_id="doc1234567890123:0000",
            doc_id="doc1234567890123",
            idx=0,
            page=None,
            page_end=None,
            sheet="Expenses",
            section="Sheet: Expenses",
            kind="table",
            location="[finance/budget.xlsx | sheet: Expenses]",
            text="| Item | Cost |\n|---|---|\n| Coffee | 25000 |",
            embed_text="budget.xlsx > Expenses\n| Item | Cost |",
            embedding=dummy_vec1,
        ),
        indexing.Chunk(
            chunk_id="doc1234567890123:0001",
            doc_id="doc1234567890123",
            idx=1,
            page=None,
            page_end=None,
            sheet="Savings",
            section="Sheet: Savings",
            kind="table",
            location="[finance/budget.xlsx | sheet: Savings]",
            text="| Fund | Target |\n|---|---|\n| Emergency | 50000000 |",
            embed_text="budget.xlsx > Savings\n| Fund | Target |",
            embedding=dummy_vec2,
        ),
    ]

    store.save_document_and_chunks(conn, doc_data, chunks)

    # Verifikasi pengambilan data
    doc = store.get_document(conn, "doc1234567890123")
    assert doc is not None
    assert doc["rel_path"] == "finance/budget.xlsx"
    assert doc["n_chunks"] == 2

    retrieved_chunks = store.get_chunks_by_doc_id(conn, "doc1234567890123")
    assert len(retrieved_chunks) == 2
    assert retrieved_chunks[0]["chunk_id"] == "doc1234567890123:0000"

    # Verifikasi FTS5 record terdaftar
    fts_rows = conn.execute("SELECT * FROM chunks_fts;").fetchall()
    assert len(fts_rows) == 2

    # Verifikasi penghapusan cascade
    store.delete_document(conn, "doc1234567890123")
    assert store.get_document(conn, "doc1234567890123") is None
    assert len(store.get_chunks_by_doc_id(conn, "doc1234567890123")) == 0
    assert len(conn.execute("SELECT * FROM chunks_fts;").fetchall()) == 0

    conn.close()


def test_build_fts_query_sanitization(tmp_path: Path):
    """Memastikan build_fts_query kebal terhadap karakter aneh, operator FTS5, dan injeksi sintaks."""
    db_file = tmp_path / "test_fts.db"
    conn = store.init_db(db_file)

    # Simpan chunk untuk pengujian kueri
    doc_data = {
        "doc_id": "testdoc12345678",
        "rel_path": "notes/tips.txt",
        "filename": "tips.txt",
        "file_type": "txt",
        "folder": "notes",
        "file_hash": "hash999",
        "size": 100,
        "mtime": 1700000000.0,
        "needs_ocr": False,
        "indexed_at": "2025-01-01T12:00:00",
    }
    chunks = [
        indexing.Chunk(
            chunk_id="testdoc12345678:0000",
            doc_id="testdoc12345678",
            idx=0,
            page=None,
            page_end=None,
            sheet=None,
            section=None,
            kind="paragraph",
            location="[notes/tips.txt]",
            text="Penggantian filter oli mesin kode SP-FLT-9902 dengan aman.",
            embed_text="tips.txt\nPenggantian filter oli mesin kode SP-FLT-9902 dengan aman.",
            embedding=np.zeros(4, dtype=np.float32),
        )
    ]
    store.save_document_and_chunks(conn, doc_data, chunks)

    # Berbagai input kueri berbahaya / bermasalah pada FTS5 biasa
    hostile_queries = [
        'SP-FLT-9902',
        '"filter" AND NOT (oli OR mesin)',
        '*** NEAR/5 "oli" :::::',
        'SELECT * FROM chunks; DROP TABLE chunks; --',
        '(((((())))))',
        '"""""',
        'dan di ke dari ini itu',  # Seluruhnya stopword
    ]

    for q in hostile_queries:
        fts_q = store.build_fts_query(q)
        # Menjalankan kueri FTS5 tidak boleh memunculkan OperationalError / syntax error
        res = store.bm25_search(conn, q)
        assert isinstance(res, list)

    # Pastikan kode suku cadang SP-FLT-9902 ditemukan
    res_code = store.bm25_search(conn, "SP-FLT-9902")
    assert len(res_code) >= 1

    conn.close()


# ==============================================================================
# 2. Test VectorIndex di Memori
# ==============================================================================


def test_vector_index_search(tmp_path: Path):
    """Memastikan pencarian vektor di memori menghitung cosine similarity dan mendukung filtering."""
    db_file = tmp_path / "test_vec.db"
    conn = store.init_db(db_file)

    doc1 = {
        "doc_id": "doc111111111111",
        "rel_path": "asuransi/polis.pdf",
        "filename": "polis.pdf",
        "file_type": "pdf",
        "folder": "asuransi",
        "file_hash": "h1",
        "size": 500,
        "mtime": 100.0,
        "needs_ocr": False,
        "indexed_at": "2025-01-01T00:00:00",
    }
    doc2 = {
        "doc_id": "doc222222222222",
        "rel_path": "rumah/sewa.docx",
        "filename": "sewa.docx",
        "file_type": "docx",
        "folder": "rumah",
        "file_hash": "h2",
        "size": 600,
        "mtime": 100.0,
        "needs_ocr": False,
        "indexed_at": "2025-01-01T00:00:00",
    }

    # Buat 2 vektor ortogonal (1, 0) dan (0, 1)
    ch1 = indexing.Chunk(
        chunk_id="doc111111111111:0000",
        doc_id="doc111111111111",
        idx=0,
        page=1,
        page_end=1,
        sheet=None,
        section="Manfaat",
        kind="paragraph",
        location="[asuransi/polis.pdf | hal. 1]",
        text="Manfaat asuransi kesehatan rawat inap",
        embed_text="polis.pdf > Manfaat\nManfaat asuransi kesehatan",
        embedding=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
    )
    ch2 = indexing.Chunk(
        chunk_id="doc222222222222:0000",
        doc_id="doc222222222222",
        idx=0,
        page=None,
        page_end=None,
        sheet=None,
        section="Sewa",
        kind="paragraph",
        location="[rumah/sewa.docx]",
        text="Perjanjian sewa rumah tahunan",
        embed_text="sewa.docx > Sewa\nPerjanjian sewa rumah",
        embedding=np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
    )

    store.save_document_and_chunks(conn, doc1, [ch1])
    store.save_document_and_chunks(conn, doc2, [ch2])

    vindex = store.VectorIndex(dtype="float32")
    vindex.load_from_db(conn)

    assert not vindex.is_empty()
    assert len(vindex.rowids) == 2

    # Query mengarah ke doc1 (1.0, 0.0, ...)
    q_vec1 = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32)
    res = vindex.search(q_vec1, k=2)
    assert len(res) == 2
    # Peringkat 1 harus doc1
    assert res[0][0] == 1
    assert res[0][1] > 0.9

    # Filter berdasarkan folder 'rumah'
    res_filtered = vindex.search(q_vec1, k=2, folder="rumah")
    assert len(res_filtered) == 1
    assert res_filtered[0][0] == 2

    # Verifikasi refresh_if_stale
    assert not vindex.refresh_if_stale(conn)  # Belum ada perubahan
    store.increment_index_version(conn)
    assert vindex.refresh_if_stale(conn)  # Terdeteksi perubahan

    conn.close()


# ==============================================================================
# 3. Test Chunking Sadar Struktur
# ==============================================================================


def test_chunking_structure():
    """Memastikan chunking tidak memotong tabel di tengah baris dan menjaga prefix konteks."""
    # 1. Tabel panjang dengan 10 baris data
    headers = "| No | Nama | Nilai |"
    sep = "|---|---|---|"
    rows = [f"| {i} | Item {i} | Rp {i * 10000} |" for i in range(1, 15)]
    full_table = "\n".join([headers, sep] + rows)

    tbl_block = Block(
        rel_path="data/tabel.md",
        file_hash="thash",
        filename="tabel.md",
        file_type="md",
        folder="data",
        modified_at="2025-01-01T00:00:00",
        kind="table",
        section="Daftar Nilai",
        text=full_table,
    )

    # Chunk size kecil (150 karakter) agar memicu pemotongan tabel
    chunks = indexing.chunk_blocks([tbl_block], chunk_size=150, chunk_overlap=20)
    assert len(chunks) > 1

    for c in chunks:
        assert c.kind == "table"
        lines = c.text.strip().splitlines()
        # Setiap chunk tabel wajib memiliki baris header dan separator
        assert lines[0] == headers
        assert lines[1] == sep
        assert len(lines) >= 3  # Minimal ada 1 baris data
        assert "tabel.md > Daftar Nilai" in c.embed_text

    # 2. Teks paragraf biasa
    para1 = Block(
        rel_path="artikel.txt",
        file_hash="ahash",
        filename="artikel.txt",
        file_type="txt",
        folder="",
        modified_at="2025-01-01T00:00:00",
        kind="paragraph",
        section=None,
        text="Paragraf pertama yang menjelaskan gambaran umum.",
    )
    para2 = Block(
        rel_path="artikel.txt",
        file_hash="ahash",
        filename="artikel.txt",
        file_type="txt",
        folder="",
        modified_at="2025-01-01T00:00:00",
        kind="paragraph",
        section=None,
        text="Paragraf kedua yang memberikan rincian tambahan.",
    )

    p_chunks = indexing.chunk_blocks([para1, para2], chunk_size=800, chunk_overlap=100)
    assert len(p_chunks) == 1
    assert "Paragraf pertama" in p_chunks[0].text
    assert "Paragraf kedua" in p_chunks[0].text
    assert p_chunks[0].embed_text.startswith("artikel.txt\n")


# ==============================================================================
# 4. Test Sinkronisasi Inkremental & Idempotensi (Mocked Embeddings)
# ==============================================================================


def mock_embed(texts: list[str], kind: str) -> list[list[float]]:
    """Mock embedding deterministik 4 dimensi."""
    results = []
    for t in texts:
        # Gunakan hash teks agar deterministik
        val = int(hashlib.md5(t.encode("utf-8")).hexdigest()[:4], 16) / 65535.0
        results.append([val, 1.0 - val, 0.5, 0.25])
    return results


def test_sync_idempotent_and_incremental(tmp_path: Path):
    """Memastikan sync bersifat idempotent, mendeteksi modifikasi, dan menghapus dokumen usang."""
    # Setup direktori sumber dokumen
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()

    file_a = docs_dir / "doc_a.txt"
    file_a.write_text("Ini isi dokumen A yang sangat penting.", encoding="utf-8")

    file_b = docs_dir / "doc_b.md"
    file_b.write_text("# Judul B\n\nPenjelasan untuk dokumen B.", encoding="utf-8")

    settings = get_settings().model_copy(update={"DOCS_DIR": docs_dir, "INDEX_DIR": index_dir})

    embed_call_count = 0

    def counting_mock_embed(texts: list[str], kind: str) -> list[list[float]]:
        nonlocal embed_call_count
        embed_call_count += len(texts)
        return mock_embed(texts, kind)

    # 1. Jalankan sync pertama (Build)
    rep1 = indexing.sync(root_dir=docs_dir, settings=settings, embed_fn=counting_mock_embed)
    assert rep1.added == 2
    assert rep1.skipped == 0
    assert rep1.total_chunks >= 2
    first_embed_calls = embed_call_count
    assert first_embed_calls >= 2

    # 2. Jalankan sync kedua (Idempotent - Fast Path)
    rep2 = indexing.sync(root_dir=docs_dir, settings=settings, embed_fn=counting_mock_embed)
    assert rep2.added == 0
    assert rep2.skipped == 2
    assert rep2.updated == 0
    # Tidak boleh ada panggilan embedding tambahan sama sekali
    assert embed_call_count == first_embed_calls

    # 3. Ubah isi file A
    file_a.write_text("Ini isi dokumen A yang telah DIPERBARUI kontennya.", encoding="utf-8")
    rep3 = indexing.sync(root_dir=docs_dir, settings=settings, embed_fn=counting_mock_embed)
    assert rep3.updated == 1
    assert rep3.skipped == 1
    assert embed_call_count > first_embed_calls

    # 4. Hapus file B dari disk
    file_b.unlink()
    rep4 = indexing.sync(root_dir=docs_dir, settings=settings, embed_fn=counting_mock_embed)
    assert rep4.deleted == 1
    assert rep4.skipped == 1

    # Verifikasi basis data bersih dari doc_b
    conn = store.get_connection(index_dir / "index.db")
    all_docs = store.get_all_documents(conn)
    assert len(all_docs) == 1
    assert all_docs[0]["filename"] == "doc_a.txt"
    conn.close()


def test_embedding_reuse_on_duplicate(tmp_path: Path):
    """Memastikan file kembar memakai ulang vektor yang sudah ada tanpa memanggil model embedding."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()

    sub1 = docs_dir / "folder1"
    sub2 = docs_dir / "folder2"
    sub1.mkdir()
    sub2.mkdir()

    # Dua file dengan nama sama dan konten identik di subfolder berbeda
    content = "Konten persis sama untuk pengujian embedding reuse."
    (sub1 / "dokumen.txt").write_text(content, encoding="utf-8")
    (sub2 / "dokumen.txt").write_text(content, encoding="utf-8")

    settings = get_settings().model_copy(update={"DOCS_DIR": docs_dir, "INDEX_DIR": index_dir})

    embed_call_count = 0

    def counting_mock_embed(texts: list[str], kind: str) -> list[list[float]]:
        nonlocal embed_call_count
        embed_call_count += len(texts)
        return mock_embed(texts, kind)

    rep = indexing.sync(root_dir=docs_dir, settings=settings, embed_fn=counting_mock_embed)
    assert rep.added == 2
    # Hanya 1 chunk yang di-embed ke API, chunk dari file kedua memakai ulang vektor file pertama!
    assert embed_call_count == 1

    conn = store.get_connection(index_dir / "index.db")
    docs = store.get_all_documents(conn)
    assert len(docs) == 2
    chunks = conn.execute("SELECT * FROM chunks;").fetchall()
    assert len(chunks) == 2
    # Vektor BLOB kedua identik dengan vektor pertama
    assert chunks[0]["embedding"] == chunks[1]["embedding"]
    conn.close()


def test_single_document_rollback_on_failure(tmp_path: Path):
    """Memastikan kegagalan pada satu dokumen di-rollback bersih tanpa merusak dokumen lainnya."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()

    (docs_dir / "doc_good.txt").write_text("Dokumen valid normal.", encoding="utf-8")
    (docs_dir / "doc_bad.txt").write_text("Dokumen yang akan gagal.", encoding="utf-8")

    settings = get_settings().model_copy(update={"DOCS_DIR": docs_dir, "INDEX_DIR": index_dir})

    def failing_mock_embed(texts: list[str], kind: str) -> list[list[float]]:
        for t in texts:
            if "doc_bad.txt" in t:
                raise RuntimeError("Simulasi error embedding kegagalan inferensi!")
        return mock_embed(texts, kind)

    rep = indexing.sync(root_dir=docs_dir, settings=settings, embed_fn=failing_mock_embed)
    assert rep.added == 1
    assert rep.failed == 1

    conn = store.get_connection(index_dir / "index.db")
    docs = store.get_all_documents(conn)
    assert len(docs) == 1
    assert docs[0]["filename"] == "doc_good.txt"

    # doc_bad tidak meninggalkan jejak di tabel chunks
    bad_chunks = conn.execute(
        "SELECT * FROM chunks WHERE doc_id LIKE '%doc_bad%';"
    ).fetchall()
    assert len(bad_chunks) == 0
    conn.close()


def test_indexing_lock_concurrency(tmp_path: Path):
    """Memastikan indexing_lock menolak proses bersamaan pada direktori indeks yang sama."""
    index_dir = tmp_path / "index"
    index_dir.mkdir()

    with indexing.indexing_lock(index_dir):
        # Percobaan acquire lock kedua dalam proses yang sama harus memunculkan RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            with indexing.indexing_lock(index_dir):
                pass
        assert "sedang berjalan" in str(exc_info.value)
