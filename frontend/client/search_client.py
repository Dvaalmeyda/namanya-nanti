"""Klien pencarian retrieval murni tanpa pemanggilan LLM."""

from typing import Any, Optional
from frontend.client.base import BaseApiClient


class SearchClient(BaseApiClient):
    """Klien untuk endpoint pencarian retrieval potongan dokumen."""

    def search(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 5,
        folders: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Melakukan pencarian retrieval dokumen berbasis hybrid, dense, atau BM25."""
        payload: dict[str, Any] = {
            "query": query,
            "mode": mode,
            "top_k": top_k,
        }

        filters: dict[str, Any] = {}
        if folders:
            filters["folders"] = folders
        if file_types:
            filters["file_types"] = file_types

        if filters:
            payload["filters"] = filters

        return self.request("POST", "/search", json_data=payload)
