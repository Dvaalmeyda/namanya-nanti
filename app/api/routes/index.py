"""Endpoint sinkronisasi pengindeksan dokumen dan pemantauan status pekerjaan."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_app_settings, get_job_manager, get_vector_index, verify_api_key
from app.api.jobs import IndexingJobManager, JobConflictError
from app.api.schemas import IndexStatusResponse, JobAcceptedResponse
from app.config import Settings
from app import store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Indexing"], dependencies=[Depends(verify_api_key)])


@router.post(
    "/index/update",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Jalankan sinkronisasi pengindeksan inkremental",
    description="Memulai pekerjaan sinkronisasi pemindaian dokumen disk dan basis data indeks secara asinkron di latar belakang. Mengembalikan HTTP 409 jika ada pekerjaan yang sedang berjalan.",
)
def trigger_index_update(
    settings: Settings = Depends(get_app_settings),
    manager: IndexingJobManager = Depends(get_job_manager),
    vindex: store.VectorIndex = Depends(get_vector_index),
) -> JobAcceptedResponse:
    """Memicu eksekusi sinkronisasi pengindeksan."""
    try:
        job_id = manager.start_job(root_dir=settings.DOCS_DIR, settings=settings, vector_index=vindex)
    except JobConflictError as conflict_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "job_conflict",
                "message": "Pekerjaan pengindeksan sedang berjalan.",
                "detail": str(conflict_err),
            },
        )

    return JobAcceptedResponse(
        job_id=job_id,
        status="running",
        message="Pekerjaan sinkronisasi pengindeksan dokumen telah dijadwalkan di latar belakang.",
    )


@router.get(
    "/index/status",
    response_model=IndexStatusResponse,
    summary="Status pekerjaan pengindeksan terakhir",
    description="Memeriksa status kemajuan pekerjaan pengindeksan latar belakang, berkas yang sedang diproses, estimasi sisa waktu (ETA), dan laporan hasil akhir.",
)
def get_index_status(
    manager: IndexingJobManager = Depends(get_job_manager),
) -> IndexStatusResponse:
    """Mengambil status progres pekerjaan pengindeksan."""
    data = manager.get_status()
    return IndexStatusResponse(**data)
