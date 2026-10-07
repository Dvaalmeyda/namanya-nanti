from unittest.mock import MagicMock
import httpx
import ollama
import pytest

from app.config import get_settings
from app import ollama_client


def test_embed_adds_prefixes(monkeypatch):
    """Memastikan embed menambahkan prefix query dan doc sesuai konfigurasi."""
    settings = get_settings()
    monkeypatch.setattr(settings, "EMBED_QUERY_PREFIX", "representasi kueri: ")
    monkeypatch.setattr(settings, "EMBED_DOC_PREFIX", "representasi dokumen: ")
    monkeypatch.setattr(settings, "EMBED_BATCH", 4)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.embeddings = [[0.1, 0.2], [0.3, 0.4]]
    mock_client.embed.return_value = mock_resp

    # Uji query prefix
    vecs = ollama_client.embed(["cari polis"], kind="query", client=mock_client)
    assert len(vecs) == 2
    mock_client.embed.assert_called_with(
        model=settings.EMBED_MODEL,
        input=["representasi kueri: cari polis"],
        keep_alive=settings.KEEP_ALIVE,
    )

    # Uji doc prefix
    ollama_client.embed(["isi pasal satu"], kind="doc", client=mock_client)
    mock_client.embed.assert_called_with(
        model=settings.EMBED_MODEL,
        input=["representasi dokumen: isi pasal satu"],
        keep_alive=settings.KEEP_ALIVE,
    )


def test_chat_passes_parameters(monkeypatch):
    """Memastikan chat meneruskan parameter think, num_ctx, num_predict, dll."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_THINK", False)
    monkeypatch.setattr(settings, "NUM_PREDICT", 256)
    monkeypatch.setattr(settings, "NUM_THREAD", 4)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.message.content = "Halo, ini jawaban uji."
    mock_resp.prompt_eval_count = 15
    mock_resp.prompt_eval_duration = 100_000_000
    mock_resp.eval_count = 20
    mock_resp.eval_duration = 200_000_000
    mock_resp.load_duration = 50_000_000
    mock_resp.total_duration = 350_000_000
    mock_client.chat.return_value = mock_resp

    messages = [{"role": "user", "content": "halo"}]
    res = ollama_client.chat(messages, stream=False, client=mock_client)

    assert isinstance(res, dict)
    assert res["content"] == "Halo, ini jawaban uji."
    assert res["prompt_eval_count"] == 15
    assert res["eval_count"] == 20

    mock_client.chat.assert_called_once_with(
        model=settings.LLM_MODEL,
        messages=messages,
        options={
            "num_ctx": settings.NUM_CTX,
            "num_predict": 256,
            "temperature": settings.TEMPERATURE,
            "num_thread": 4,
        },
        keep_alive=settings.KEEP_ALIVE,
        think=False,
        stream=False,
    )


def test_error_handling_model_not_found():
    """Memastikan ModelNotFound dinaikkan saat mendapat ResponseError 404."""
    mock_client = MagicMock()
    mock_client.chat.side_effect = ollama.ResponseError("model not found", status_code=404)

    with pytest.raises(ollama_client.ModelNotFound, match="belum diunduh"):
        ollama_client.chat([{"role": "user", "content": "test"}], client=mock_client)


def test_error_handling_ollama_unavailable():
    """Memastikan OllamaUnavailable dinaikkan saat koneksi gagal."""
    mock_client = MagicMock()
    mock_client.list.side_effect = httpx.ConnectError("Connection refused")

    with pytest.raises(ollama_client.OllamaUnavailable, match="tidak dapat dihubungi"):
        ollama_client.list_models(client=mock_client)
