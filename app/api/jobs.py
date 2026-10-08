"""Manajer pekerjaan pengindeksan dokumen latar belakang (Background Indexing Job Manager).

Mengelola eksekusi pekerjaan sinkronisasi indeks secara asinkron di thread terpisah,
melacak progres berkas, persentase kemajuan, estimasi sisa waktu (ETA), serta
mencegah eksekusi bersamaan (menghasilkan HTTP 409 jika bentrok).
"""

from datetime import datetime
import logging
from pathlib import Path
import threading
import time
from typing import Any, Optional
import uuid

from app.config import Settings, get_settings
from app.indexing import sync
from app import store

logger = logging.getLogger(__name__)


class JobConflictError(Exception):
    """Pengecualian saat ada upaya menjalankan pekerjaan baru ketika pekerjaan lain masih berjalan."""


class IndexingJobManager:
    """Manajer status dan eksekusi pekerjaan sinkronisasi pengindeksan."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status: str = "idle"  # idle | running | completed | failed
        self.job_id: Optional[str] = None
        self.current_file: Optional[str] = None
        self.current_index: int = 0
        self.total_files: int = 0
        self.progress_percent: float = 0.0
        self.eta_seconds: Optional[float] = None
        self.report: Optional[dict[str, Any]] = None
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.errors: list[str] = []
        self._start_time: float = 0.0

    def is_running(self) -> bool:
        """Memeriksa apakah pekerjaan sedang berjalan."""
        with self._lock:
            return self.status == "running"

    def get_status(self) -> dict[str, Any]:
        """Mengembalikan salinan kamus status pekerjaan saat ini."""
        with self._lock:
            return {
                "status": self.status,
                "job_id": self.job_id,
                "progress_percent": self.progress_percent,
                "current_file": self.current_file,
                "current_index": self.current_index,
                "total_files": self.total_files,
                "eta_seconds": self.eta_seconds,
                "report": self.report,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "errors": list(self.errors),
            }

    def start_job(
        self,
        root_dir: Optional[Path] = None,
        settings: Optional[Settings] = None,
        vector_index: Optional[store.VectorIndex] = None,
    ) -> str:
        """Memulai pekerjaan sinkronisasi pengindeksan di thread latar belakang."""
        if settings is None:
            settings = get_settings()

        target_root = root_dir if root_dir is not None else settings.DOCS_DIR
        new_job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        with self._lock:
            if self.status == "running":
                raise JobConflictError(
                    f"Pekerjaan pengindeksan '{self.job_id}' sedang berjalan. "
                    "Harap tunggu hingga pekerjaan selesai sebelum memulai yang baru."
                )

            self.status = "running"
            self.job_id = new_job_id
            self.current_file = None
            self.current_index = 0
            self.total_files = 0
            self.progress_percent = 0.0
            self.eta_seconds = None
            self.report = None
            self.started_at = datetime.now().isoformat()
            self.completed_at = None
            self.errors = []
            self._start_time = time.time()

        def _worker() -> None:
            logger.info("Memulai pekerjaan pengindeksan latar belakang [%s]", new_job_id)

            def _progress_cb(rel_path: str, idx: int, total: int) -> None:
                with self._lock:
                    self.current_file = rel_path
                    self.current_index = idx
                    self.total_files = total
                    self.progress_percent = round((idx / max(total, 1)) * 100.0, 1)

                    elapsed = time.time() - self._start_time
                    if idx > 0 and total > idx:
                        avg_per_file = elapsed / idx
                        self.eta_seconds = round(avg_per_file * (total - idx), 1)
                    else:
                        self.eta_seconds = 0.0

            try:
                rep = sync(
                    root_dir=target_root,
                    settings=settings,
                    progress_cb=_progress_cb,
                )

                # Segarkan matriks VectorIndex jika tersedia
                db_path = settings.INDEX_DIR / "index.db"
                if vector_index is not None and db_path.exists():
                    try:
                        conn = store.get_connection(db_path)
                        vector_index.refresh_if_stale(conn)
                        conn.close()
                        logger.info("VectorIndex berhasil disegarkan setelah sinkronisasi.")
                    except Exception as exc:
                        logger.warning("Gagal menyegarkan VectorIndex: %s", exc)

                rep_dict = {
                    "added": rep.added,
                    "updated": rep.updated,
                    "deleted": rep.deleted,
                    "skipped": rep.skipped,
                    "failed": rep.failed,
                    "total_chunks": rep.total_chunks,
                    "duration_s": round(rep.duration_s, 2),
                    "chunks_per_sec": round(rep.chunks_per_sec, 1),
                }

                with self._lock:
                    self.status = "completed"
                    self.progress_percent = 100.0
                    self.eta_seconds = 0.0
                    self.current_file = None
                    self.report = rep_dict
                    self.completed_at = datetime.now().isoformat()
                    if rep.errors:
                        self.errors.extend(rep.errors)

                logger.info(
                    "Pekerjaan pengindeksan [%s] selesai dalam %.2f detik (total chunks: %d)",
                    new_job_id,
                    rep.duration_s,
                    rep.total_chunks,
                )

            except Exception as exc:
                err_msg = str(exc)
                logger.error("Pekerjaan pengindeksan [%s] gagal: %s", new_job_id, err_msg)
                with self._lock:
                    self.status = "failed"
                    self.completed_at = datetime.now().isoformat()
                    self.errors.append(err_msg)

        thread = threading.Thread(target=_worker, name=f"indexer-{new_job_id}", daemon=True)
        thread.start()
        return new_job_id


# Instance global singleton JobManager
job_manager = IndexingJobManager()


def get_job_manager() -> IndexingJobManager:
    """Mengembalikan instance singleton IndexingJobManager."""
    return job_manager
