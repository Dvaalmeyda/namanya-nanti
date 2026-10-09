"""Klien pemantauan kesehatan sistem, status indeks, dan pembacaan log."""

from typing import Any, Optional
from frontend.client.base import BaseApiClient


class SystemClient(BaseApiClient):
    """Klien untuk endpoint status sistem, sinkronisasi indeks, dan log."""

    def get_health(self) -> dict[str, Any]:
        """Memeriksa status operasional sistem, Ollama, dan indeks."""
        return self.request("GET", "/health")

    def get_index_status(self) -> dict[str, Any]:
        """Mengambil kemajuan dan status pekerjaan sinkronisasi indeks saat ini."""
        return self.request("GET", "/index/status")

    def trigger_index_update(self) -> dict[str, Any]:
        """Menjadwalkan pekerjaan pembaruan indeks di latar belakang."""
        return self.request("POST", "/index/update")

    def get_system_logs(
        self,
        lines: int = 100,
        level: Optional[str] = None,
        search: Optional[str] = None,
    ) -> dict[str, Any]:
        """Mengambil cuplikan log sistem dari backend terfilter."""
        params: dict[str, Any] = {"lines": lines}
        if level and level.upper() != "ALL":
            params["level"] = level
        if search:
            params["search"] = search
        return self.request("GET", "/system/logs", params=params)
