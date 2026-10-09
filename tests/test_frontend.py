"""Unit test untuk frontend Streamlit (Fase 6: Frontend).

Menguji utilitas pemformatan, parser SSE, batasan baris kode (<200 LOC),
kepatuhan aturan anti-emotikon, dan interaksi klien API dengan mock.
"""

from pathlib import Path
import re
from typing import Any
import pytest

from frontend.client.base import ApiClientError, BaseApiClient
from frontend.client.chat_client import ChatClient
from frontend.client.document_client import DocumentClient
from frontend.client.search_client import SearchClient
from frontend.client.system_client import SystemClient
from frontend.utils.formatters import (
    format_badge,
    format_bytes,
    format_datetime,
    format_ms,
    format_speed,
)
from frontend.utils.sse_parser import parse_sse_stream


# ==============================================================================
# 1. Test Formatters
# ==============================================================================


def test_format_ms():
    """Memastikan format_ms memformat angka milidetik dan detik dengan benar."""
    assert format_ms(None) == "-"
    assert format_ms(150.4) == "150.4 ms"
    assert format_ms(2450.0) == "2.45 s"


def test_format_bytes():
    """Memastikan format_bytes mengonversi byte ke KB dan MB secara presisi."""
    assert format_bytes(None) == "-"
    assert format_bytes(500) == "500 B"
    assert format_bytes(1024 * 50) == "50.0 KB"
    assert format_bytes(1024 * 1024 * 5) == "5.0 MB"


def test_format_speed_and_badge():
    """Memastikan format kecepatan dan badge status teks tanpa emotikon."""
    assert format_speed(None) == "-"
    assert format_speed(6.23) == "6.2 tok/s"

    assert format_badge("ok") == "[OK]"
    assert format_badge("error") == "[ERROR]"
    assert format_badge("dirujuk") == "[DIRUJUK]"
    assert format_badge("tidak dirujuk") == "[TIDAK DIRUJUK]"
    assert format_badge("lolos") == "[LOLOS]"
    assert format_badge("ditolak") == "[DITOLAK]"


# ==============================================================================
# 2. Test SSE Parser
# ==============================================================================


def test_sse_parser_events():
    """Memastikan parse_sse_stream mengurai event token, sources, dan done."""
    raw_sse_lines = [
        "event: token\n",
        'data: {"content": "Halo "}\n',
        "\n",
        "event: token\n",
        'data: {"content": "dunia"}\n',
        "\n",
        "event: sources\n",
        'data: {"sources": [{"n": 1, "filename": "doc.pdf"}]}\n',
        "\n",
        "event: done\n",
        'data: {"refused": false, "timing": {"total_ms": 1200.0}}\n',
        "\n",
    ]

    events = list(parse_sse_stream(iter(raw_sse_lines)))
    assert len(events) == 4

    assert events[0].event == "token"
    assert events[0].data["content"] == "Halo "

    assert events[1].event == "token"
    assert events[1].data["content"] == "dunia"

    assert events[2].event == "sources"
    assert len(events[2].data["sources"]) == 1

    assert events[3].event == "done"
    assert events[3].data["refused"] is False


# ==============================================================================
# 3. Test Architectural Constraints: LOC & No Emoticons
# ==============================================================================


def test_frontend_loc_constraint():
    """Memastikan tidak ada berkas di direktori frontend yang melebihi 200 baris kode."""
    frontend_dir = Path("frontend")
    py_files = list(frontend_dir.rglob("*.py"))
    assert len(py_files) >= 15, "Harus terdapat berkas-berkas modular di frontend/"

    for f in py_files:
        lines = f.read_text(encoding="utf-8").splitlines()
        loc = len(lines)
        assert loc <= 200, f"Berkas {f} melebihi batas 200 baris (ditemukan: {loc} baris)"


def test_frontend_no_emoticons_constraint():
    """Memastikan seluruh berkas kode frontend bebas dari karakter emotikon/emoji."""
    # Rentang Unicode untuk emoji umum dan simbol grafis
    emoji_pattern = re.compile(
        r"[\U0001F600-\U0001F64F"  # Emoticons
        r"\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
        r"\U0001F680-\U0001F6FF"  # Transport and Map
        r"\U0001F700-\U0001F77F"  # Alchemical Symbols
        r"\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        r"\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        r"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        r"\U0001FA00-\U0001FA6F"  # Chess Symbols
        r"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        r"\U00002702-\U000027B0"  # Dingbats
        r"\U000024C2-\U0001F251]"
    )

    frontend_dir = Path("frontend")
    for f in frontend_dir.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        matches = emoji_pattern.findall(text)
        assert len(matches) == 0, f"Berkas {f} memuat emotikon: {matches}"


# ==============================================================================
# 4. Test API Clients with Mock
# ==============================================================================


def test_api_clients_mock(monkeypatch: pytest.MonkeyPatch):
    """Memastikan kelas-kelas klien API mengonstruksi payload dan memanggil request."""
    recorded_calls = []

    def mock_request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        recorded_calls.append({"method": method, "path": path, "kwargs": kwargs})
        if path == "/health":
            return {"status": "ok", "document_count": 5}
        elif path == "/documents":
            return {"documents": [{"doc_id": "doc1", "filename": "test.pdf"}]}
        elif path == "/search":
            return {"total_hits": 1, "hits": []}
        elif path == "/chat":
            return {"answer": "Jawaban [1]", "sources": [], "timing": {}}
        return {"status": "success"}

    monkeypatch.setattr(BaseApiClient, "request", mock_request)

    # 1. SystemClient
    sys_client = SystemClient(base_url="http://127.0.0.1:8000/api/v1")
    health = sys_client.get_health()
    assert health["status"] == "ok"

    # 2. DocumentClient
    doc_client = DocumentClient(base_url="http://127.0.0.1:8000/api/v1")
    docs = doc_client.get_documents(folder="rumah")
    assert len(docs) == 1

    # 3. SearchClient
    search_client = SearchClient(base_url="http://127.0.0.1:8000/api/v1")
    search_res = search_client.search("sewa", mode="hybrid")
    assert search_res["total_hits"] == 1

    # 4. ChatClient
    chat_client = ChatClient(base_url="http://127.0.0.1:8000/api/v1")
    chat_res = chat_client.chat_sync("Berapa biaya sewa?")
    assert "Jawaban" in chat_res["answer"]
