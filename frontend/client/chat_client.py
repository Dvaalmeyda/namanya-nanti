"""Klien eksekusi tanya-jawab RAG non-streaming dan streaming SSE."""

from collections.abc import Generator
from typing import Any, Optional
import httpx

from frontend.client.base import ApiClientError, BaseApiClient
from frontend.utils.sse_parser import SseEvent, parse_sse_stream


class ChatClient(BaseApiClient):
    """Klien untuk endpoint chat interaktif asisten dokumen."""

    def _build_payload(
        self,
        question: str,
        history: Optional[list[dict[str, str]]] = None,
        folders: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
        top_k: int = 4,
        include_chunks: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": question,
            "top_k": top_k,
            "include_chunks": include_chunks,
        }
        if history:
            payload["history"] = history

        filters: dict[str, Any] = {}
        if folders:
            filters["folders"] = folders
        if file_types:
            filters["file_types"] = file_types
        if filters:
            payload["filters"] = filters

        return payload

    def chat_sync(
        self,
        question: str,
        history: Optional[list[dict[str, str]]] = None,
        folders: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
        top_k: int = 4,
        include_chunks: bool = True,
    ) -> dict[str, Any]:
        """Menjalankan tanya-jawab RAG non-streaming dan mengembalikan JSON utuh."""
        payload = self._build_payload(
            question=question,
            history=history,
            folders=folders,
            file_types=file_types,
            top_k=top_k,
            include_chunks=include_chunks,
        )
        return self.request("POST", "/chat", json_data=payload)

    def chat_stream(
        self,
        question: str,
        history: Optional[list[dict[str, str]]] = None,
        folders: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
        top_k: int = 4,
    ) -> Generator[SseEvent, None, None]:
        """Menjalankan tanya-jawab RAG streaming dan mengalirkan event SSE."""
        payload = self._build_payload(
            question=question,
            history=history,
            folders=folders,
            file_types=file_types,
            top_k=top_k,
            include_chunks=False,
        )
        url = f"{self.base_url}/chat/stream"
        headers = self._get_headers()
        headers["Accept"] = "text/event-stream"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        self._handle_error_response(resp)
                    yield from parse_sse_stream(resp.iter_lines())
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            msg = f"Koneksi streaming ke backend terputus: {exc}"
            raise ApiClientError(msg, details=str(exc)) from exc
