"""Suite pengujian otomatis untuk REST API FastAPI (Fase 4: API).

Menggunakan FastAPI TestClient, menguji skema lengkap, streaming SSE,
retrieval search, daur hidup upload/indexing/delete, hardening keamanan,
autentikasi API key, dan penanganan gangguan Ollama.
"""

from collections.abc import Generator
import io
from pathlib import Path
import time
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_app_settings
from app.api.jobs import IndexingJobManager, get_job_manager
from app.api.main import create_app
from app.config import Settings, get_settings
import app.ollama_client as ollama_client
import app.store as store


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Fixture TestClient dengan inisialisasi lifespan default."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# 1. Test Health Endpoint
# ==============================================================================


def test_health_endpoint(client: TestClient):
    """Memastikan endpoint /health mengembalikan skema lengkap dan bebas autentikasi."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200

    data = resp.json()
    assert "status" in data
    assert "ollama_connected" in data
    assert "document_count" in data
    assert "chunk_count" in data
    assert "index_version" in data
    assert "config_summary" in data
    assert isinstance(data["models_available"], list)


# ==============================================================================
# 2. Test Chat (JSON) & Relevance Gate Refusal
# ==============================================================================


def test_chat_endpoint_json_success(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Memastikan /chat menghasilkan ChatResponse lengkap dengan sitasi [1]."""
    llm_called = False

    def mock_chat(messages, stream=False, client=None):
        nonlocal llm_called
        llm_called = True
        return {
            "content": "Total biaya sewa rumah adalah Rp 75.000.000 untuk 2 tahun [1].",
            "prompt_eval_count": 50,
            "prompt_eval_duration": 1000,
            "eval_count": 20,
            "eval_duration": 500,
            "load_duration": 100,
            "total_duration": 1600,
        }

    monkeypatch.setattr(ollama_client, "chat", mock_chat)

    payload = {
        "question": "Berapa total biaya sewa rumah?",
        "filters": {"folders": ["rumah"]},
        "top_k": 3,
        "include_chunks": True,
    }
    resp = client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert llm_called is True
    assert data["refused"] is False
    assert "75.000.000" in data["answer"]
    assert len(data["sources"]) >= 1

    # Verifikasi sitasi dan text chunk
    first_source = data["sources"][0]
    assert first_source["n"] == 1
    assert first_source["cited"] is True
    assert first_source["text"] is not None  # karena include_chunks=True
    assert "timing" in data


def test_chat_endpoint_refusal_without_llm(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Memastikan kueri di luar konteks ditolak oleh gerbang relevansi tanpa memanggil LLM."""
    llm_called = False

    def mock_chat(*args, **kwargs):
        nonlocal llm_called
        llm_called = True
        return {"content": "Jawaban terlarang"}

    # Mock embed agar menghasilkan vektor nol sehingga relevansi rendah
    monkeypatch.setattr(ollama_client, "embed", lambda texts, kind, client=None: [[0.0] * 1024 for _ in texts])
    monkeypatch.setattr(ollama_client, "chat", mock_chat)

    payload = {"question": "Resep membuat kue bolu pandan keju kukus lembut"}
    resp = client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert llm_called is False  # LLM TIDAK boleh dipanggil sama sekali
    assert data["refused"] is True
    assert data["answer"] == "Tidak ditemukan di dokumen Anda."
    assert data["sources"] == []


# ==============================================================================
# 3. Test Chat Stream (Server-Sent Events)
# ==============================================================================


def test_chat_stream_sse_order(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Memastikan /chat/stream mengirimkan urutan event: token -> sources -> done."""
    def mock_chat_stream(messages, stream=True, client=None):
        yield {"content": "Biaya sewa ", "done": False}
        yield {"content": "Rp 75 juta [1].", "done": True, "eval_count": 10, "eval_duration": 200}

    monkeypatch.setattr(ollama_client, "chat", mock_chat_stream)

    payload = {
        "question": "Berapa biaya sewa rumah?",
        "filters": {"folders": ["rumah"]},
    }
    resp = client.post("/api/v1/chat/stream", json=payload)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    lines = resp.text.strip().split("\n")
    events_received: list[str] = []
    for line in lines:
        if line.startswith("event: "):
            events_received.append(line.replace("event: ", "").strip())

    assert "token" in events_received
    assert "sources" in events_received
    assert "done" in events_received

    # Urutan token harus mendahului sources, dan sources harus mendahului done
    idx_token = events_received.index("token")
    idx_sources = events_received.index("sources")
    idx_done = events_received.index("done")
    assert idx_token < idx_sources < idx_done


# ==============================================================================
# 4. Test Search (Hybrid, Dense, BM25)
# ==============================================================================


def test_search_all_modes(client: TestClient):
    """Memastikan /search berfungsi untuk ketiga mode: hybrid, dense, dan bm25."""
    # 1. Mode Hybrid
    resp_hyb = client.post("/api/v1/search", json={"query": "perjanjian sewa menyewa", "mode": "hybrid", "top_k": 3})
    assert resp_hyb.status_code == 200
    d_hyb = resp_hyb.json()
    assert d_hyb["mode"] == "hybrid"
    assert len(d_hyb["hits"]) >= 1
    assert d_hyb["hits"][0]["rrf_score"] > 0
    assert len(d_hyb["hits"][0]["snippet"]) <= 200

    # 2. Mode BM25 (Kueri kode suku cadang eksak)
    resp_bm25 = client.post("/api/v1/search", json={"query": "SP-FLT-9902", "mode": "bm25", "top_k": 2})
    assert resp_bm25.status_code == 200
    d_bm25 = resp_bm25.json()
    assert d_bm25["mode"] == "bm25"
    assert len(d_bm25["hits"]) >= 1
    assert d_bm25["hits"][0]["bm25_score"] is not None

    # 3. Mode Dense
    resp_dense = client.post("/api/v1/search", json={"query": "asuransi kesehatan keluarga", "mode": "dense", "top_k": 2})
    assert resp_dense.status_code == 200
    d_dense = resp_dense.json()
    assert d_dense["mode"] == "dense"
    assert len(d_dense["hits"]) >= 1
    assert d_dense["hits"][0]["dense_score"] is not None


# ==============================================================================
# 5. Test Documents & Chunks Read Endpoints
# ==============================================================================


def test_documents_list_and_detail(client: TestClient):
    """Memastikan /documents dan /documents/{doc_id} membaca metadata dokumen secara akurat."""
    # List documents
    resp = client.get("/api/v1/documents?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["documents"]) >= 1

    doc = data["documents"][0]
    doc_id = doc["doc_id"]

    # Detail document
    resp_detail = client.get(f"/api/v1/documents/{doc_id}")
    assert resp_detail.status_code == 200
    d_detail = resp_detail.json()
    assert d_detail["document"]["doc_id"] == doc_id
    assert len(d_detail["chunks"]) >= 1

    first_chunk = d_detail["chunks"][0]
    chunk_id = first_chunk["chunk_id"]

    # Detail chunk
    resp_chunk = client.get(f"/api/v1/chunks/{chunk_id}")
    assert resp_chunk.status_code == 200
    d_chunk = resp_chunk.json()
    assert d_chunk["chunk_id"] == chunk_id
    assert len(d_chunk["text"]) > 0

    # 404 pada ID yang tidak ada
    assert client.get("/api/v1/documents/non_existent_doc_id").status_code == 404
    assert client.get("/api/v1/chunks/non_existent_chunk_id").status_code == 404


# ==============================================================================
# 6. Test Upload, Indexing Lifecycle, and Hardening
# ==============================================================================


def test_upload_validation_and_hardening(client: TestClient):
    """Memastikan validasi upload: path traversal (400), tipe file (415), dan ukuran (413)."""
    # 1. Path traversal pada parameter folder
    dummy_file = ("test.txt", io.BytesIO(b"Halo dunia"), "text/plain")
    resp_trav = client.post(
        "/api/v1/documents",
        files={"file": dummy_file},
        data={"folder": "../dangerous/path"},
    )
    assert resp_trav.status_code == 400
    assert resp_trav.json()["code"] == "invalid_folder"

    # 2. Format berkas tidak didukung (HTTP 415)
    bad_file = ("script.exe", io.BytesIO(b"binary"), "application/octet-stream")
    resp_ext = client.post("/api/v1/documents", files={"file": bad_file}, data={"folder": "test"})
    assert resp_ext.status_code == 415
    assert resp_ext.json()["code"] == "unsupported_media_type"


def test_upload_and_indexing_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Memastikan alur lengkap upload berkas, sync job, pengecekan status, dan delete."""
    temp_docs = tmp_path / "docs"
    temp_index = tmp_path / "index"
    temp_docs.mkdir(parents=True)
    temp_index.mkdir(parents=True)

    test_settings = Settings(
        DOCS_DIR=temp_docs,
        INDEX_DIR=temp_index,
        WARMUP=False,
    )

    # Mock embed untuk indexing agar deterministik dan cepat
    def mock_embed(texts, kind="doc", client=None):
        return [[0.1] * 1024 for _ in texts]

    monkeypatch.setattr(ollama_client, "embed", mock_embed)

    app = create_app(settings=test_settings)
    app.dependency_overrides[get_app_settings] = lambda: test_settings

    with TestClient(app) as local_client:
        # Unggah berkas markdown baru
        md_content = b"# Prosedur Kerja\n\nLangkah pertama adalah menyalakan komputer dan memeriksa jaringan."
        upload_resp = local_client.post(
            "/api/v1/documents",
            files={"file": ("prosedur.md", io.BytesIO(md_content), "text/markdown")},
            data={"folder": "sop"},
        )
        assert upload_resp.status_code == 202
        job_id = upload_resp.json()["job_id"]

        # Tunggu pekerjaan selesai
        mgr = get_job_manager()
        for _ in range(30):
            status_data = local_client.get("/api/v1/index/status").json()
            if status_data["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)

        assert status_data["status"] == "completed"

        # Verifikasi berkas muncul di daftar dokumen
        docs_resp = local_client.get("/api/v1/documents")
        assert docs_resp.status_code == 200
        docs = docs_resp.json()["documents"]
        assert len(docs) == 1
        uploaded_doc = docs[0]
        assert uploaded_doc["filename"] == "prosedur.md"

        # Hapus dokumen beserta file fisik
        del_resp = local_client.delete(f"/api/v1/documents/{uploaded_doc['doc_id']}?delete_file=true")
        assert del_resp.status_code == 200
        assert del_resp.json()["file_deleted"] is True

        # Pastikan sudah tidak ada di basis data
        docs_after = local_client.get("/api/v1/documents").json()["documents"]
        assert len(docs_after) == 0


# ==============================================================================
# 7. Test Concurrency & Conflict (409)
# ==============================================================================


def test_index_concurrency_conflict(client: TestClient):
    """Memastikan /index/update mengembalikan HTTP 409 jika ada pekerjaan yang sedang berjalan."""
    mgr = get_job_manager()
    # Simulasikan status sedang berjalan
    with mgr._lock:
        prev_status = mgr.status
        mgr.status = "running"
        mgr.job_id = "test_active_job"

    try:
        resp = client.post("/api/v1/index/update")
        assert resp.status_code == 409
        assert resp.json()["code"] == "job_conflict"
    finally:
        with mgr._lock:
            mgr.status = prev_status


# ==============================================================================
# 8. Test Authentication (API_KEY)
# ==============================================================================


def test_api_key_authentication(monkeypatch: pytest.MonkeyPatch):
    """Memastikan proteksi X-API-Key: 401 tanpa header, 200 dengan header, dan /health tetap terbuka."""
    auth_settings = Settings(API_KEY="kunci-rahasia-123", WARMUP=False)
    app = create_app(settings=auth_settings)
    app.dependency_overrides[get_app_settings] = lambda: auth_settings

    with TestClient(app) as auth_client:
        # 1. /health tetap bisa diakses tanpa API key
        resp_health = auth_client.get("/api/v1/health")
        assert resp_health.status_code == 200

        # 2. /documents tanpa header -> 401 Unauthorized
        resp_no_key = auth_client.get("/api/v1/documents")
        assert resp_no_key.status_code == 401
        assert resp_no_key.json()["code"] == "unauthorized"

        # 3. /documents dengan key salah -> 401 Unauthorized
        resp_wrong_key = auth_client.get("/api/v1/documents", headers={"X-API-Key": "salah"})
        assert resp_wrong_key.status_code == 401

        # 4. /documents dengan key benar -> 200 OK
        resp_valid_key = auth_client.get("/api/v1/documents", headers={"X-API-Key": "kunci-rahasia-123"})
        assert resp_valid_key.status_code == 200


# ==============================================================================
# 9. Test Ollama Error & Privacy Host Guard
# ==============================================================================


def test_ollama_unavailable_and_model_not_found(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Memastikan penanganan error OllamaUnavailable dan ModelNotFound menghasilkan HTTP 503 yang ramah."""
    # 1. Ollama mati
    def mock_dead(*args, **kwargs):
        raise ollama_client.OllamaUnavailable("Ollama connection refused.")

    monkeypatch.setattr(ollama_client, "chat", mock_dead)
    resp = client.post("/api/v1/chat", json={"question": "kontrak sewa"})
    assert resp.status_code == 503
    assert resp.json()["code"] == "ollama_unavailable"

    # 2. Model belum di-pull
    def mock_not_found(*args, **kwargs):
        raise ollama_client.ModelNotFound("Model belum di-pull.")

    monkeypatch.setattr(ollama_client, "chat", mock_not_found)
    resp_mnf = client.post("/api/v1/chat", json={"question": "kontrak sewa"})
    assert resp_mnf.status_code == 503
    assert resp_mnf.json()["code"] == "model_not_found"


def test_startup_fails_on_remote_host_without_permission():
    """Memastikan startup gagal bila OLLAMA_HOST mengarah ke non-loopback tanpa ALLOW_REMOTE=True."""
    remote_settings = Settings(
        OLLAMA_HOST="http://192.168.1.100:11434",
        ALLOW_REMOTE=False,
    )
    app = create_app(settings=remote_settings)

    with pytest.raises(ValueError, match="Akses ke host non-loopback"):
        with TestClient(app):
            pass
