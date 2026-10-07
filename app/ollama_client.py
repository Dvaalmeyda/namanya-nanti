import logging
import time
from typing import Any, Generator, Literal, Optional, Union

import httpx
import ollama

from app.config import get_settings

logger = logging.getLogger(__name__)


class OllamaClientError(Exception):
    """Kelas dasar error untuk klien Ollama."""


class OllamaUnavailable(OllamaClientError):
    """Error ketika instance server Ollama tidak dapat dihubungi."""


class ModelNotFound(OllamaClientError):
    """Error ketika model LLM atau embedding belum diunduh (pull)."""


def get_client() -> ollama.Client:
    """Membuat instance klien resmi Ollama berbasis konfigurasi."""
    settings = get_settings()
    return ollama.Client(
        host=settings.OLLAMA_HOST,
        timeout=settings.OLLAMA_TIMEOUT_S,
    )


def _handle_ollama_error(err: Exception, model_name: str = "") -> None:
    """Mengonversi error eksternal menjadi exception spesifik aplikasi."""
    if isinstance(err, (httpx.ConnectError, httpx.ConnectTimeout)):
        settings = get_settings()
        raise OllamaUnavailable(
            f"Ollama tidak dapat dihubungi di {settings.OLLAMA_HOST}. "
            "Pastikan aplikasi atau server service Ollama sedang berjalan di komputer lokal."
        ) from err
    if isinstance(err, ollama.ResponseError):
        if err.status_code == 404:
            target_model = model_name or "yang diminta"
            raise ModelNotFound(
                f"Model '{target_model}' belum diunduh. "
                f"Silakan jalankan perintah terminal: ollama pull {target_model}"
            ) from err
    raise OllamaClientError(f"Terjadi kesalahan saat berkomunikasi dengan Ollama: {err}") from err


def list_models(client: Optional[ollama.Client] = None) -> list[str]:
    """Mengambil daftar nama model yang tersedia di server Ollama."""
    c = client or get_client()
    try:
        response = c.list()
        models: list[str] = []
        for m in getattr(response, "models", []):
            name = getattr(m, "model", None) or getattr(m, "name", "")
            if name:
                models.append(name)
        return models
    except Exception as e:
        _handle_ollama_error(e)
        return []


def loaded_models(client: Optional[ollama.Client] = None) -> list[dict[str, Any]]:
    """Mengambil status model yang sedang aktif di memori (VRAM/RAM) dari /api/ps."""
    c = client or get_client()
    try:
        response = c.ps()
        results: list[dict[str, Any]] = []
        for m in getattr(response, "models", []):
            results.append({
                "model": getattr(m, "model", ""),
                "size": getattr(m, "size", 0),
                "size_vram": getattr(m, "size_vram", 0),
                "expires_at": str(getattr(m, "expires_at", "")),
            })
        return results
    except Exception as e:
        _handle_ollama_error(e)
        return []


def embed(
    texts: list[str],
    kind: Literal["query", "doc"] = "doc",
    client: Optional[ollama.Client] = None,
) -> list[list[float]]:
    """Menghitung embedding vektor untuk kumpulan teks dengan batching dan prefix opsional."""
    if not texts:
        return []

    settings = get_settings()
    c = client or get_client()
    model = settings.EMBED_MODEL

    prefix = settings.EMBED_QUERY_PREFIX if kind == "query" else settings.EMBED_DOC_PREFIX
    prefixed_texts = [f"{prefix}{t}" if prefix else t for t in texts]

    batch_size = max(1, settings.EMBED_BATCH)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(prefixed_texts), batch_size):
        batch = prefixed_texts[i : i + batch_size]
        max_retries = 3
        delay = 0.5

        for attempt in range(max_retries):
            try:
                resp = c.embed(
                    model=model,
                    input=batch,
                    keep_alive=settings.KEEP_ALIVE,
                )
                embeddings = getattr(resp, "embeddings", None) or resp.get("embeddings", [])
                all_embeddings.extend(embeddings)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    _handle_ollama_error(e, model_name=model)
                logger.warning("Percobaan embed ke-%d gagal, mencoba lagi dalam %.1fs...", attempt + 1, delay)
                time.sleep(delay)
                delay *= 2

    return all_embeddings


def chat(
    messages: list[dict[str, str]],
    stream: bool = False,
    client: Optional[ollama.Client] = None,
) -> Union[dict[str, Any], Generator[dict[str, Any], None, None]]:
    """Mengirim pesan chat ke model LLM Ollama dengan parameter dan timing terpantau."""
    settings = get_settings()
    c = client or get_client()
    model = settings.LLM_MODEL

    options: dict[str, Any] = {
        "num_ctx": settings.NUM_CTX,
        "num_predict": settings.NUM_PREDICT,
        "temperature": settings.TEMPERATURE,
    }
    if settings.NUM_THREAD is not None:
        options["num_thread"] = settings.NUM_THREAD

    try:
        if not stream:
            resp = c.chat(
                model=model,
                messages=messages,
                options=options,
                keep_alive=settings.KEEP_ALIVE,
                think=settings.LLM_THINK,
                stream=False,
            )

            # Ekstraksi pesan dan metrik
            msg_obj = getattr(resp, "message", None)
            content = getattr(msg_obj, "content", "") if msg_obj else ""

            return {
                "content": content,
                "prompt_eval_count": getattr(resp, "prompt_eval_count", 0),
                "prompt_eval_duration": getattr(resp, "prompt_eval_duration", 0),
                "eval_count": getattr(resp, "eval_count", 0),
                "eval_duration": getattr(resp, "eval_duration", 0),
                "load_duration": getattr(resp, "load_duration", 0),
                "total_duration": getattr(resp, "total_duration", 0),
            }
        else:
            stream_gen = c.chat(
                model=model,
                messages=messages,
                options=options,
                keep_alive=settings.KEEP_ALIVE,
                think=settings.LLM_THINK,
                stream=True,
            )

            def _generator() -> Generator[dict[str, Any], None, None]:
                for chunk in stream_gen:
                    msg_obj = getattr(chunk, "message", None)
                    token = getattr(msg_obj, "content", "") if msg_obj else ""
                    yield {
                        "content": token,
                        "done": getattr(chunk, "done", False),
                        "prompt_eval_count": getattr(chunk, "prompt_eval_count", 0),
                        "prompt_eval_duration": getattr(chunk, "prompt_eval_duration", 0),
                        "eval_count": getattr(chunk, "eval_count", 0),
                        "eval_duration": getattr(chunk, "eval_duration", 0),
                    }

            return _generator()

    except Exception as e:
        _handle_ollama_error(e, model_name=model)
        raise


def warmup(client: Optional[ollama.Client] = None) -> dict[str, Any]:
    """Memuat model LLM dan embedding ke memori untuk menghindari latensi dingin pada kueri awal."""
    settings = get_settings()
    c = client or get_client()

    t0 = time.perf_counter()
    embed_ok = False
    llm_ok = False

    try:
        embed(["ping uji warm-up"], kind="query", client=c)
        embed_ok = True
    except Exception as e:
        logger.warning("Gagal melakukan warmup model embedding: %s", e)

    try:
        chat([{"role": "user", "content": "ping"}], stream=False, client=c)
        llm_ok = True
    except Exception as e:
        logger.warning("Gagal melakukan warmup model LLM: %s", e)

    dur_ms = (time.perf_counter() - t0) * 1000
    return {
        "embed_warm": embed_ok,
        "llm_warm": llm_ok,
        "duration_ms": round(dur_ms, 2),
    }
