import os
import pytest
from app.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Mengosongkan cache get_settings sebelum dan sesudah tiap tes."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
