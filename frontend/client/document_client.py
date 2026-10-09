"""Klien pengelolaan dokumen, pengunggahan berkas, dan inspeksi teks chunk."""

from typing import Any, Optional
from frontend.client.base import BaseApiClient


class DocumentClient(BaseApiClient):
    """Klien untuk endpoint pengelolaan dokumen dan potongan teks."""

    def get_documents(
        self, folder: Optional[str] = None, timeout: float = 5.0
    ) -> list[dict[str, Any]]:
        """Mengambil daftar seluruh dokumen yang telah terindeks."""
        params: dict[str, Any] = {}
        if folder:
            params["folder"] = folder
        res = self.request("GET", "/documents", params=params, timeout=timeout)
        return res.get("documents", [])

    def get_document(self, doc_id: str) -> dict[str, Any]:
        """Mengambil informasi detail satu dokumen beserta daftar ID chunk."""
        return self.request("GET", f"/documents/{doc_id}")

    def upload_document(
        self,
        file_name: str,
        file_bytes: bytes,
        folder: Optional[str] = None,
    ) -> dict[str, Any]:
        """Mengunggah berkas dokumen baru ke direktori data backend."""
        files = {"file": (file_name, file_bytes)}
        data: dict[str, Any] = {}
        if folder:
            data["folder"] = folder
        return self.request("POST", "/documents", files=files, data=data)

    def delete_document(self, doc_id: str) -> dict[str, Any]:
        """Menghapus dokumen dan seluruh potongan teksnya dari indeks."""
        return self.request("DELETE", f"/documents/{doc_id}")

    def get_chunk(self, chunk_id: str) -> dict[str, Any]:
        """Mengambil teks lengkap dari satu potongan dokumen berdasarkan chunk_id."""
        return self.request("GET", f"/chunks/{chunk_id}")
