"""Modul penyimpanan lokal SQLite WAL, FTS5 (BM25), dan indeks vektor NumPy di memori."""

import logging
from pathlib import Path
import re
import sqlite3
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

ID_STOPWORDS = {
    "dan", "di", "ke", "dari", "ini", "itu", "untuk", "pada",
    "adalah", "yang", "dengan", "atau", "oleh", "dalam", "akan",
    "juga", "sudah", "saya", "kami", "mereka", "dia", "anda",
}


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Membuka koneksi SQLite dengan konfigurasi WAL dan foreign keys aktif."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    """Menginisialisasi tabel basis data dokumen, chunks, FTS5, dan settings."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                rel_path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                folder TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                n_chunks INTEGER NOT NULL,
                needs_ocr INTEGER NOT NULL DEFAULT 0,
                indexed_at TEXT NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_rel_path ON documents(rel_path);")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT UNIQUE NOT NULL,
                doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                idx INTEGER NOT NULL,
                page INTEGER,
                page_end INTEGER,
                sheet TEXT,
                section TEXT,
                kind TEXT NOT NULL,
                location TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);")

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                fts_text,
                tokenize='unicode61 remove_diacritics 2'
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        # Inisialisasi default index_version jika belum ada
        conn.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('schema_version', '1.0');
        """)
        conn.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('index_version', '0');
        """)

    return conn


def get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """Mengambil nilai konfigurasi dari tabel settings."""
    cur = conn.execute("SELECT value FROM settings WHERE key = ?;", (key,))
    row = cur.fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Menyimpan atau memperbarui nilai konfigurasi di tabel settings."""
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
        (key, value),
    )


def get_all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    """Mengambil seluruh pasangan key-value konfigurasi."""
    cur = conn.execute("SELECT key, value FROM settings;")
    return {row["key"]: row["value"] for row in cur.fetchall()}


def increment_index_version(conn: sqlite3.Connection) -> int:
    """Menaikkan index_version secara atomik untuk sinkronisasi cache memori."""
    cur_ver = int(get_setting(conn, "index_version") or "0")
    new_ver = cur_ver + 1
    set_setting(conn, "index_version", str(new_ver))
    return new_ver


# ==============================================================================
# Operasi Dokumen & Chunk
# ==============================================================================


def get_document(conn: sqlite3.Connection, doc_id: str) -> Optional[dict[str, Any]]:
    """Mengambil metadata dokumen berdasarkan doc_id."""
    cur = conn.execute("SELECT * FROM documents WHERE doc_id = ?;", (doc_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_document_by_rel_path(conn: sqlite3.Connection, rel_path: str) -> Optional[dict[str, Any]]:
    """Mengambil metadata dokumen berdasarkan path relatif."""
    cur = conn.execute("SELECT * FROM documents WHERE rel_path = ?;", (rel_path,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_all_documents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Mengambil seluruh catatan metadata dokumen."""
    cur = conn.execute("SELECT * FROM documents ORDER BY rel_path ASC;")
    return [dict(row) for row in cur.fetchall()]


def get_documents_by_hash(conn: sqlite3.Connection, file_hash: str) -> list[dict[str, Any]]:
    """Mencari dokumen yang memiliki konten hash identik."""
    cur = conn.execute("SELECT * FROM documents WHERE file_hash = ?;", (file_hash,))
    return [dict(row) for row in cur.fetchall()]


def get_chunks_by_doc_id(conn: sqlite3.Connection, doc_id: str) -> list[dict[str, Any]]:
    """Mengambil seluruh chunk milik dokumen tertentu."""
    cur = conn.execute("SELECT * FROM chunks WHERE doc_id = ? ORDER BY idx ASC;", (doc_id,))
    return [dict(row) for row in cur.fetchall()]


def get_chunk_by_rowid(conn: sqlite3.Connection, rowid: int) -> Optional[dict[str, Any]]:
    """Mengambil detail satu chunk berdasarkan rowid."""
    cur = conn.execute("SELECT * FROM chunks WHERE rowid = ?;", (rowid,))
    row = cur.fetchone()
    return dict(row) if row else None


def delete_document(conn: sqlite3.Connection, doc_id: str) -> None:
    """Menghapus dokumen dan membersihkan relasi chunks serta FTS5."""
    with conn:
        # Bersihkan FTS5 secara eksplisit sebelum penghapusan CASCADE
        conn.execute(
            "DELETE FROM chunks_fts WHERE rowid IN (SELECT rowid FROM chunks WHERE doc_id = ?);",
            (doc_id,),
        )
        conn.execute("DELETE FROM documents WHERE doc_id = ?;", (doc_id,))
        increment_index_version(conn)


def save_document_and_chunks(
    conn: sqlite3.Connection,
    doc_data: dict[str, Any],
    chunks: list[Any],
) -> None:
    """Menyimpan dokumen dan kumpulan chunk secara atomik dalam satu transaksi."""
    doc_id = doc_data["doc_id"]
    with conn:
        # 1. Hapus entri lama jika dokumen sudah ada
        conn.execute(
            "DELETE FROM chunks_fts WHERE rowid IN (SELECT rowid FROM chunks WHERE doc_id = ?);",
            (doc_id,),
        )
        conn.execute("DELETE FROM documents WHERE doc_id = ?;", (doc_id,))

        # 2. Sisipkan dokumen baru
        conn.execute(
            """
            INSERT INTO documents (
                doc_id, rel_path, filename, file_type, folder,
                file_hash, size, mtime, n_chunks, needs_ocr, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                doc_id,
                doc_data["rel_path"],
                doc_data["filename"],
                doc_data["file_type"],
                doc_data["folder"],
                doc_data["file_hash"],
                doc_data["size"],
                doc_data["mtime"],
                len(chunks),
                int(doc_data.get("needs_ocr", False)),
                doc_data["indexed_at"],
            ),
        )

        # 3. Sisipkan chunk dan indeks FTS5
        for ch in chunks:
            raw_emb = ch.embedding
            emb_blob = raw_emb.astype(np.float32).tobytes() if isinstance(raw_emb, np.ndarray) else b""

            cur = conn.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, idx, page, page_end,
                    sheet, section, kind, location, text, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    ch.chunk_id,
                    doc_id,
                    ch.idx,
                    ch.page,
                    ch.page_end,
                    ch.sheet,
                    ch.section,
                    ch.kind,
                    ch.location,
                    ch.text,
                    emb_blob,
                ),
            )
            chunk_rowid = cur.lastrowid

            # Konten FTS5 = nama file + section + teks chunk
            fts_parts = [doc_data["filename"]]
            if ch.section:
                fts_parts.append(ch.section)
            fts_parts.append(ch.text)
            fts_text = " ".join(fts_parts)

            conn.execute(
                "INSERT INTO chunks_fts (rowid, fts_text) VALUES (?, ?);",
                (chunk_rowid, fts_text),
            )

        increment_index_version(conn)


# ==============================================================================
# Pencarian BM25 (FTS5)
# ==============================================================================


def build_fts_query(text: str) -> str:
    """Membangun kueri FTS5 yang aman dari karakter khusus dan injeksi sintaks."""
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return ""

    # Filter stopword bahasa Indonesia dan deduplikasi
    seen = set()
    valid_tokens = []
    for t in tokens:
        if t not in ID_STOPWORDS and t not in seen:
            seen.add(t)
            valid_tokens.append(t)

    if not valid_tokens:
        # Jika semua token adalah stopword, gunakan token asli tanpa stopword filter
        valid_tokens = list(dict.fromkeys(tokens))

    # Bungkus setiap token dalam tanda kutip ganda dan gabung dengan OR
    return " OR ".join(f'"{token}"' for token in valid_tokens)


def bm25_search(
    conn: sqlite3.Connection,
    query_text: str,
    k: int = 5,
    folder: Optional[str] = None,
    file_type: Optional[str] = None,
    folders: Optional[Any] = None,
    file_types: Optional[Any] = None,
    doc_ids: Optional[Any] = None,
) -> list[tuple[int, float]]:
    """Mencari chunk menggunakan BM25 pada tabel chunks_fts dengan dukungan filter."""
    fts_query = build_fts_query(query_text)
    if not fts_query:
        return []

    sql = """
        SELECT c.rowid, -bm25(chunks_fts) AS score
        FROM chunks_fts f
        JOIN chunks c ON f.rowid = c.rowid
        JOIN documents d ON c.doc_id = d.doc_id
        WHERE chunks_fts MATCH ?
    """
    params: list[Any] = [fts_query]

    # Normalisasi filter
    all_folders = [folder] if folder else ([folders] if isinstance(folders, str) else (folders or []))
    all_types = [file_type] if file_type else ([file_types] if isinstance(file_types, str) else (file_types or []))
    all_docs = [doc_ids] if isinstance(doc_ids, str) else (doc_ids or [])

    if all_folders:
        placeholders = ",".join(["?"] * len(all_folders))
        sql += f" AND d.folder IN ({placeholders})"
        params.extend(all_folders)

    if all_types:
        clean_types = [t.lower() for t in all_types]
        placeholders = ",".join(["?"] * len(clean_types))
        sql += f" AND d.file_type IN ({placeholders})"
        params.extend(clean_types)

    if all_docs:
        placeholders = ",".join(["?"] * len(all_docs))
        sql += f" AND d.doc_id IN ({placeholders})"
        params.extend(all_docs)

    sql += " ORDER BY score DESC LIMIT ?;"
    params.append(k)

    cur = conn.execute(sql, params)
    return [(row["rowid"], float(row["score"])) for row in cur.fetchall()]


# ==============================================================================
# Indeks Vektor di Memori (VectorIndex)
# ==============================================================================


class VectorIndex:
    """Indeks vektor berbasis matriks NumPy di RAM dengan normalisasi L2 dan cosine top-k."""

    def __init__(self, dtype: str = "float32"):
        self.dtype = np.float16 if dtype == "float16" else np.float32
        self.matrix: Optional[np.ndarray] = None  # (N, D)
        self.rowids: np.ndarray = np.array([], dtype=np.int64)
        self.chunk_ids: list[str] = []
        self.doc_ids: list[str] = []
        self.folders: list[str] = []
        self.file_types: list[str] = []
        self.cached_version: str = "-1"

    def is_empty(self) -> bool:
        """Memeriksa apakah indeks vektor belum memuat data."""
        return self.matrix is None or len(self.rowids) == 0

    def load_from_db(self, conn: sqlite3.Connection) -> None:
        """Memuat seluruh embedding dari SQLite ke matriks NumPy memori."""
        cur = conn.execute("""
            SELECT c.rowid, c.chunk_id, c.doc_id, c.embedding, d.folder, d.file_type
            FROM chunks c
            JOIN documents d ON c.doc_id = d.doc_id
            WHERE length(c.embedding) > 0
            ORDER BY c.rowid ASC;
        """)
        rows = cur.fetchall()

        if not rows:
            self.matrix = None
            self.rowids = np.array([], dtype=np.int64)
            self.chunk_ids = []
            self.doc_ids = []
            self.folders = []
            self.file_types = []
            self.cached_version = get_setting(conn, "index_version") or "0"
            return

        rowids_list: list[int] = []
        chunk_ids_list: list[str] = []
        doc_ids_list: list[str] = []
        folders_list: list[str] = []
        file_types_list: list[str] = []
        vectors_list: list[np.ndarray] = []

        for r in rows:
            blob = r["embedding"]
            vec = np.frombuffer(blob, dtype=np.float32)
            rowids_list.append(r["rowid"])
            chunk_ids_list.append(r["chunk_id"])
            doc_ids_list.append(r["doc_id"])
            folders_list.append(r["folder"])
            file_types_list.append(r["file_type"])
            vectors_list.append(vec)

        # Matriks (N, D)
        raw_matrix = np.vstack(vectors_list)

        # L2-normalization untuk menghitung cosine similarity melalui dot product
        norms = np.linalg.norm(raw_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        normalized_matrix = raw_matrix / norms

        self.matrix = normalized_matrix.astype(self.dtype)
        self.rowids = np.array(rowids_list, dtype=np.int64)
        self.chunk_ids = chunk_ids_list
        self.doc_ids = doc_ids_list
        self.folders = folders_list
        self.file_types = file_types_list
        self.cached_version = get_setting(conn, "index_version") or "0"

    def refresh_if_stale(self, conn: sqlite3.Connection) -> bool:
        """Memeriksa apakah versi basis data berubah dan menyegarkan memori jika stale."""
        current_version = get_setting(conn, "index_version") or "0"
        if current_version != self.cached_version or self.is_empty():
            self.load_from_db(conn)
            return True
        return False

    def search(
        self,
        query_vec: np.ndarray,
        k: int = 5,
        folder: Optional[str] = None,
        file_type: Optional[str] = None,
        folders: Optional[Any] = None,
        file_types: Optional[Any] = None,
        doc_ids: Optional[Any] = None,
    ) -> list[tuple[int, float]]:
        """Mencari top-k tetangga terdekat menggunakan dot product vektor ternormalisasi dengan filter."""
        if self.is_empty() or self.matrix is None:
            return []

        # Normalisasi query vector
        q = query_vec.astype(self.dtype)
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm

        n_samples = len(self.rowids)
        mask = np.ones(n_samples, dtype=bool)

        # Normalisasi filter
        all_folders = [folder] if folder else ([folders] if isinstance(folders, str) else (folders or []))
        all_types = [file_type] if file_type else ([file_types] if isinstance(file_types, str) else (file_types or []))
        all_docs = [doc_ids] if isinstance(doc_ids, str) else (doc_ids or [])

        if all_folders:
            f_set = set(all_folders)
            mask &= np.array([f in f_set for f in self.folders], dtype=bool)
        if all_types:
            ft_set = {t.lower() for t in all_types}
            mask &= np.array([ft in ft_set for ft in self.file_types], dtype=bool)
        if all_docs:
            d_set = set(all_docs)
            mask &= np.array([did in d_set for did in self.doc_ids], dtype=bool)

        valid_indices = np.where(mask)[0]
        if len(valid_indices) == 0:
            return []

        sub_matrix = self.matrix[valid_indices]
        scores = sub_matrix @ q

        top_k = min(k, len(scores))
        if top_k <= 0:
            return []

        # Gunakan argpartition untuk efisiensi O(N) dibandingkan sort penuh O(N log N)
        if len(scores) > top_k:
            partitioned = np.argpartition(-scores, top_k - 1)[:top_k]
            sorted_part = partitioned[np.argsort(-scores[partitioned])]
        else:
            sorted_part = np.argsort(-scores)

        results: list[tuple[int, float]] = []
        for idx in sorted_part:
            orig_idx = valid_indices[idx]
            results.append((int(self.rowids[orig_idx]), float(scores[idx])))

        return results
