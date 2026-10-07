# FASE 1 - Loader dan normalisasi dokumen

> Prasyarat: Fase 0 selesai.
> Baca `00-KONTEKS.md` terlebih dahulu.

## TUGAS
Bangun `app/loaders.py` yang membaca dokumen dan menghasilkan `Block` ternormalisasi.

### Skema dataclass `Block`
| Field | Tipe | Keterangan |
|---|---|---|
| `rel_path` | str | Path relatif terhadap root dokumen, pemisah `/`. **Kunci identitas dokumen.** |
| `file_hash` | str | sha256 isi file (untuk deteksi perubahan, bukan identitas) |
| `filename` | str | Nama file |
| `file_type` | str | `pdf` / `docx` / `xlsx` / `md` / `txt` |
| `folder` | str | Folder tingkat pertama di bawah root (kosong bila di root); dipakai sebagai filter |
| `modified_at` | str | mtime ISO 8601 |
| `page` | int \| None | Nomor halaman 1-based, **hanya PDF** |
| `sheet` | str \| None | Nama sheet, **hanya XLSX** |
| `section` | str | Jalur heading (`Pasal 2 > Pembayaran`) atau nama sheet |
| `kind` | str | `heading` / `paragraph` / `table` / `list` |
| `text` | str | Isi blok |
| `needs_ocr` | bool | True bila halaman PDF tampaknya hasil scan |

Fungsi `format_location(block) -> str` menghasilkan label sitasi sesuai tipe: `hlm. 3` (PDF), `sheet "Tabungan"` (XLSX), `bagian "Pasal 2 > Pembayaran"` (DOCX/MD/TXT; kosong bila tanpa heading).

### Langkah
1. **Format**: PDF, DOCX, XLSX, MD, TXT.
2. **Backend PDF** lewat config `PDF_BACKEND`:
   - `pymupdf` (default): teks per halaman + `page.find_tables()`; area tabel tidak boleh terbaca dua kali sebagai paragraf.
   - `pymupdf4llm` (opsional): keluaran Markdown per halaman. Pasang hanya bila diaktifkan, lalu bandingkan kualitas tabel dan waktu proses dengan default.
3. **DOCX** (python-docx): iterasi elemen body **sesuai urutan dokumen** (paragraf dan tabel bergantian, lewat `document.element.body`), bukan `doc.paragraphs` lalu `doc.tables` terpisah. Heading dideteksi dari style bawaan Heading 1-9 (cek juga `outline level`, karena nama style bisa terlokalisasi). `page=None`.
4. **XLSX** (openpyxl): buka dengan `read_only=True, data_only=True`. Lewati baris dan kolom kosong. Tanggal diformat ISO, angka apa adanya. Satu Block `kind=table` per potongan sekitar 30 baris, header diulang di setiap potongan. `sheet` dan `section` berisi nama sheet.
5. **MD**: pisahkan per heading, `section` berisi jalur heading. **TXT**: per paragraf. Encoding: UTF-8, fallback `cp1252`.
6. **Tabel** selalu menjadi satu Block `kind=table` berformat Markdown dengan baris header.
7. **PDF hasil scan**: bila teks per halaman sangat sedikit (ambang di config), set `needs_ocr=True`, catat peringatan di log, dan **jangan** OCR.
8. **Batas ukuran**: `MAX_FILE_MB` (default 50); file lebih besar dilewati dengan peringatan.
9. **Fungsi publik**:
   - `scan_dir(root) -> list[Path]`: rekursif, abaikan file sementara (`~$*`, `.~lock*`), file tersembunyi, dan ekstensi yang tidak didukung.
   - `load_file(path, root) -> list[Block]`.
   - `file_hash(path) -> str` (dibaca bertahap, aman untuk file besar).
10. **CLI**: `python -m app.loaders data/sample --stats` mencetak per file: jumlah blok per kind, jumlah halaman/sheet, `needs_ocr`, waktu proses. Isi teks hanya dicetak dengan `--preview` (maksimal 200 karakter per blok).

## BATASAN
- Belum ada chunking, embedding, atau penyimpanan (itu Fase 2).
- Error pada satu file tidak boleh menghentikan pemindaian: catat (nama file + jenis error, tanpa isi) dan lanjut.
- Tidak ada akses jaringan.

## KRITERIA SELESAI
- Tes tiap format dengan dokumen di `data/sample/`:
  - Tabel PDF utuh sebagai satu Block `table` dan tidak terduplikasi sebagai paragraf.
  - Heading DOCX terbaca di `section`; tabel DOCX muncul di posisi yang benar di antara paragraf.
  - Kedua sheet XLSX terbaca dengan **nilai angka** (bukan rumus atau `None`).
  - Dua file kembar (`asuransi/` dan `arsip/`) menghasilkan Block dengan `rel_path` berbeda dan `file_hash` sama.
  - `format_location` benar untuk setiap tipe.
- Laporkan waktu proses per file. Bila `pymupdf4llm` dicoba, laporkan perbandingan singkat kualitas tabel dan kecepatan.
