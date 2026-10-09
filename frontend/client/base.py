"""Klien HTTP dasar dengan penanganan autentikasi, batas waktu, dan galat koneksi."""

from typing import Any, Optional
import httpx

from frontend.config import config


class ApiClientError(Exception):
    """Galat umum komunikasi dengan backend API."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class BaseApiClient:
    """Klien HTTP terpusat untuk membungkus panggilan REST API FastAPI."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or config.backend_api_url).rstrip("/")
        self.api_key = api_key if api_key is not None else config.api_key
        self.timeout = config.timeout_seconds

    def _get_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Menjalankan permintaan HTTP sinkron dengan penanganan galat terstruktur."""
        url = f"{self.base_url}{path}"
        headers = self._get_headers()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    files=files,
                    data=data,
                )

                if resp.status_code in (200, 202):
                    return resp.json()

                self._handle_error_response(resp)
                return {}

        except httpx.ConnectError as exc:
            msg = f"Tidak dapat terhubung ke backend FastAPI di {self.base_url}. Pastikan server menyala."
            raise ApiClientError(msg, details=str(exc)) from exc
        except httpx.TimeoutException as exc:
            msg = f"Batas waktu permintaan terlampaui ({self.timeout}s)."
            raise ApiClientError(msg, details=str(exc)) from exc

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Menguraikan respons error HTTP ke pesan yang informatif."""
        try:
            err_data = resp.json()
            detail = err_data.get("detail", str(err_data))
        except Exception:
            detail = resp.text

        if resp.status_code == 401:
            msg = "Autentikasi gagal: API Key tidak valid atau tidak disertakan."
        elif resp.status_code == 404:
            msg = "Sumber daya tidak ditemukan di backend."
        elif resp.status_code == 409:
            msg = "Konflik status: pekerjaan lain sedang berjalan."
        elif resp.status_code == 503:
            msg = "Layanan Ollama lokal tidak tersedia atau model belum di-pull."
        else:
            msg = f"Galat HTTP {resp.status_code}: {detail}"

        raise ApiClientError(msg, status_code=resp.status_code, details=detail)
