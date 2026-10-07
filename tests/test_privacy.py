import os
import pytest

from app.config import get_settings
from app.privacy import apply_offline_env, assert_local_only


def test_apply_offline_env():
    """Memastikan flag offline lingkungan diatur dengan benar."""
    apply_offline_env()
    assert os.environ.get("ANONYMIZED_TELEMETRY") == "False"
    assert os.environ.get("DO_NOT_TRACK") == "1"
    assert os.environ.get("HF_HUB_OFFLINE") == "1"
    assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"


def test_assert_local_only_allowed():
    """Memastikan URL loopback diizinkan secara default."""
    assert_local_only("http://127.0.0.1:11434")
    assert_local_only("http://localhost:11434")
    assert_local_only("http://[::1]:11434")


def test_assert_local_only_rejected():
    """Memastikan host remote ditolak ketika ALLOW_REMOTE=False."""
    with pytest.raises(ValueError, match="Akses ke host non-loopback"):
        assert_local_only("http://api.openai.com/v1")

    with pytest.raises(ValueError, match="Akses ke host non-loopback"):
        assert_local_only("http://192.168.1.100:11434")


def test_assert_local_only_when_remote_allowed(monkeypatch):
    """Memastikan host remote diizinkan jika ALLOW_REMOTE=True."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ALLOW_REMOTE", True)
    # Tidak boleh melempar ValueError
    assert_local_only("http://192.168.1.100:11434")
