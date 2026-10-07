"""Unit test untuk modul app/loaders (Fase 1: Loader dan Normalisasi Dokumen)."""

from pathlib import Path
import tempfile
import pytest
import pymupdf

from app.config import get_settings
from app.loaders import (
    Block,
    compute_file_hash,
    format_location,
    format_table_as_markdown,
    get_file_metadata,
    load_documents,
    load_file,
    scan_directory,
)


def test_scan_directory(tmp_path: Path):
    """Memastikan scan_directory menyaring file yang didukung dan mengabaikan hidden/temp/oversized."""
    # File yang valid
    (tmp_path / "doc1.pdf").write_bytes(b"%PDF-1.4 dummy")
    (tmp_path / "doc2.docx").write_bytes(b"dummy docx")
    (tmp_path / "data.xlsx").write_bytes(b"dummy xlsx")
    (tmp_path / "notes.md").write_text("# Notes", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("Hello world", encoding="utf-8")

    # File/folder yang harus diabaikan
    (tmp_path / ".hidden.pdf").write_bytes(b"%PDF-1.4 hidden")
    hidden_dir = tmp_path / ".hidden_folder"
    hidden_dir.mkdir()
    (hidden_dir / "inside.pdf").write_bytes(b"%PDF-1.4 inside")

    (tmp_path / "~$temp_office.docx").write_bytes(b"temp docx")
    (tmp_path / "image.png").write_bytes(b"fake png")
    (tmp_path / "archive.zip").write_bytes(b"fake zip")

    # File besar melebihi batas 1MB
    large_file = tmp_path / "large.pdf"
    large_file.write_bytes(b"A" * (2 * 1024 * 1024))  # 2MB

    scanned = scan_directory(tmp_path, max_file_mb=1)
    scanned_names = [f.name for f in scanned]

    assert "doc1.pdf" in scanned_names
    assert "doc2.docx" in scanned_names
    assert "data.xlsx" in scanned_names
    assert "notes.md" in scanned_names
    assert "readme.txt" in scanned_names

    assert ".hidden.pdf" not in scanned_names
    assert "inside.pdf" not in scanned_names
    assert "~$temp_office.docx" not in scanned_names
    assert "image.png" not in scanned_names
    assert "archive.zip" not in scanned_names
    assert "large.pdf" not in scanned_names  # melebihi 1MB


def test_file_hash_and_metadata(tmp_path: Path):
    """Memastikan kalkulasi hash dan ekstraksi metadata bekerja konsisten."""
    test_file = tmp_path / "subfolder" / "sample.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("Konten dokumen pengujian", encoding="utf-8")

    hash1 = compute_file_hash(test_file)
    assert len(hash1) == 64  # SHA-256 hex string

    meta = get_file_metadata(test_file, root_dir=tmp_path)
    assert meta["rel_path"] == "subfolder/sample.txt"
    assert meta["file_hash"] == hash1
    assert meta["filename"] == "sample.txt"
    assert meta["file_type"] == "txt"
    assert meta["folder"] == "subfolder"
    assert "T" in meta["modified_at"]  # Format ISO 8601


def test_format_location():
    """Memastikan format lokasi menghasilkan string sitasi yang presisi."""
    # Kasus PDF dengan nomor halaman dan section
    b_pdf = Block(
        rel_path="asuransi/polis.pdf",
        file_hash="abc",
        filename="polis.pdf",
        file_type="pdf",
        folder="asuransi",
        modified_at="2025-01-01T10:00:00",
        page=2,
        section="Tabel Manfaat",
    )
    assert format_location(b_pdf) == "[asuransi/polis.pdf | hal. 2 | Tabel Manfaat]"

    # Kasus XLSX dengan sheet
    b_xlsx = Block(
        rel_path="keuangan/anggaran.xlsx",
        file_hash="def",
        filename="anggaran.xlsx",
        file_type="xlsx",
        folder="keuangan",
        modified_at="2025-01-01T10:00:00",
        sheet="Pengeluaran",
        section="Sheet: Pengeluaran",
    )
    assert format_location(b_xlsx) == "[keuangan/anggaran.xlsx | sheet: Pengeluaran]"

    # Kasus DOCX dengan section
    b_docx = Block(
        rel_path="kontrak/perjanjian.docx",
        file_hash="ghi",
        filename="perjanjian.docx",
        file_type="docx",
        folder="kontrak",
        modified_at="2025-01-01T10:00:00",
        section="Pasal 2",
    )
    assert format_location(b_docx) == "[kontrak/perjanjian.docx | Pasal 2]"

    # Kasus TXT tanpa metadata halaman
    b_txt = Block(
        rel_path="catatan.txt",
        file_hash="jkl",
        filename="catatan.txt",
        file_type="txt",
        folder="",
        modified_at="2025-01-01T10:00:00",
    )
    assert format_location(b_txt) == "[catatan.txt]"


def test_format_table_as_markdown():
    """Memastikan konversi tabel matriks ke representasi Markdown table rapi."""
    headers = ["Nama", "Jumlah", "Keterangan"]
    rows = [["Barang A", "10", "Stok cukup"], ["Barang B", "5", "Perlu restock"]]
    md = format_table_as_markdown(headers, rows)

    assert "| Nama | Jumlah | Keterangan |" in md
    assert "| --- | --- | --- |" in md
    assert "| Barang A | 10 | Stok cukup |" in md
    assert "| Barang B | 5 | Perlu restock |" in md


def test_extract_pdf_sample():
    """Memastikan ekstraksi file sample PDF mempertahankan tabel dan tidak menduplikasi teks."""
    pdf_path = Path("data/sample/asuransi/polis-kesehatan.pdf")
    assert pdf_path.exists(), "File sample PDF harus tersedia"

    blocks = load_file(pdf_path, root_dir=Path("data/sample"))
    assert len(blocks) > 0

    # Cek keberadaan halaman 1 dan 2
    pages = {b.page for b in blocks if b.page is not None}
    assert 1 in pages
    assert 2 in pages

    # Cek tabel pada halaman 2
    table_blocks = [b for b in blocks if b.kind == "table"]
    assert len(table_blocks) >= 1

    tbl = table_blocks[0]
    assert "| Jenis Manfaat | Limit Maksimal | Ketentuan Khusus |" in tbl.text
    assert "Rp 150.000.000 / tahun" in tbl.text

    # Pastikan teks baris tabel tidak muncul lagi sebagai blok paragraf biasa
    para_blocks = [b for b in blocks if b.kind == "paragraph" and b.page == 2]
    for p in para_blocks:
        assert "Rp 150.000.000 / tahun" not in p.text


def test_extract_docx_sample():
    """Memastikan ekstraksi DOCX berjalan sekuensial untuk paragraf, heading, dan tabel."""
    docx_path = Path("data/sample/rumah/kontrak-sewa.docx")
    assert docx_path.exists(), "File sample DOCX harus tersedia"

    blocks = load_file(docx_path, root_dir=Path("data/sample"))
    assert len(blocks) >= 5

    kinds = [b.kind for b in blocks]
    assert "heading" in kinds
    assert "paragraph" in kinds
    assert "table" in kinds

    # Cek tabel jadwal pembayaran
    table_blocks = [b for b in blocks if b.kind == "table"]
    assert len(table_blocks) == 1
    assert "Tahap Pembayaran" in table_blocks[0].text
    assert "Rp 25.000.000" in table_blocks[0].text


def test_extract_xlsx_sample():
    """Memastikan ekstraksi spreadsheet XLSX membaca semua sheet dan menjaga integritas nilai angka."""
    xlsx_path = Path("data/sample/keuangan/anggaran-rumah-tangga.xlsx")
    assert xlsx_path.exists(), "File sample XLSX harus tersedia"

    blocks = load_file(xlsx_path, root_dir=Path("data/sample"))
    assert len(blocks) >= 2

    sheets = {b.sheet for b in blocks}
    assert "Pengeluaran 2025" in sheets
    assert "Tabungan" in sheets

    # Pastikan nilai numerik bukan rumus mentah atau None
    all_text = "\n".join(b.text for b in blocks)
    assert "6500000" in all_text
    assert "100000000" in all_text
    assert "Dana Darurat" in all_text


def test_extract_md_sample():
    """Memastikan file Markdown diekstrak dengan preservasi hierarki heading dan list."""
    md_path = Path("data/sample/kendaraan/catatan-servis.md")
    assert md_path.exists(), "File sample MD harus tersedia"

    blocks = load_file(md_path, root_dir=Path("data/sample"))
    assert len(blocks) >= 4

    kinds = [b.kind for b in blocks]
    assert "heading" in kinds
    assert "list" in kinds

    # Cek konten servis
    all_text = "\n".join(b.text for b in blocks)
    assert "SP-FLT-9902" in all_text
    assert "Honda Pasteur Bandung" in all_text


def test_extract_txt_sample():
    """Memastikan ekstraksi file TXT membaca paragraf secara teratur."""
    txt_path = Path("data/sample/unduhan/artikel-tips.txt")
    assert txt_path.exists(), "File sample TXT harus tersedia"

    blocks = load_file(txt_path, root_dir=Path("data/sample"))
    assert len(blocks) >= 2
    for b in blocks:
        assert b.kind == "paragraph"


def test_load_documents_and_deduplication():
    """Memastikan load_documents mendeteksi dokumen duplikat dan menghitung statistik dengan benar."""
    sample_dir = Path("data/sample")
    blocks, stats = load_documents(sample_dir)

    assert stats["total_scanned_files"] == 6
    assert stats["loaded_files_count"] == 6
    assert len(stats["failed_files"]) == 0
    assert len(stats["duplicates"]) == 1

    # arsip/polis-kesehatan.pdf dan asuransi/polis-kesehatan.pdf identik
    dup = stats["duplicates"][0]
    assert "polis-kesehatan.pdf" in dup["original"]
    assert "polis-kesehatan.pdf" in dup["duplicate"]
    assert dup["original"] != dup["duplicate"]

    assert stats["total_blocks"] > 30
    assert stats["total_chars"] > 2000
    assert "pdf" in stats["blocks_by_type"]
    assert "table" in stats["blocks_by_kind"]


def test_corrupt_file_resilience(tmp_path: Path):
    """Memastikan sistem tahan terhadap file korup tanpa crash pada folder keseluruhan."""
    # Buat file pdf korup (hanya teks acak yang bukan PDF valid)
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"Bukan PDF yang valid sama sekali 1234567890")

    # load_file pada file korup harus mengembalikan list kosong
    res = load_file(corrupt_pdf, root_dir=tmp_path)
    assert res == []

    # Buat 1 file valid di samping file korup
    valid_txt = tmp_path / "valid.txt"
    valid_txt.write_text("Teks valid untuk pengujian keandalan", encoding="utf-8")

    # load_documents harus memuat file valid dan mencatat file korup di failed_files
    blocks, stats = load_documents(tmp_path)
    assert len(blocks) >= 1
    assert "corrupt.pdf" in stats["failed_files"]
    assert stats["loaded_files_count"] == 1


def test_scanned_pdf_needs_ocr(tmp_path: Path):
    """Memastikan halaman PDF yang hanya berisi gambar terdeteksi dengan needs_ocr=True."""
    pdf_path = tmp_path / "scanned_document.pdf"
    doc = pymupdf.open()
    page = doc.new_page()

    # Sisipkan gambar dummy 100x100 tanpa teks apa pun
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
    pix.clear_with(255)  # Warna putih
    img_rect = pymupdf.Rect(50, 50, 200, 200)
    page.insert_image(img_rect, pixmap=pix)

    doc.save(str(pdf_path))
    doc.close()

    settings = get_settings()
    blocks = load_file(pdf_path, root_dir=tmp_path, settings=settings)

    ocr_blocks = [b for b in blocks if b.needs_ocr]
    assert len(ocr_blocks) == 1
    assert "memerlukan OCR" in ocr_blocks[0].text
    assert ocr_blocks[0].page == 1
