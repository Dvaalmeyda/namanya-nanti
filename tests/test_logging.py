import logging
from app.config import get_settings
from app.logging_setup import RedactionFilter


def test_redaction_filter_censors_sensitive_attributes(monkeypatch):
    """Memastikan atribut sensitif disensor jika LOG_CONTENT=False."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LOG_CONTENT", False)

    filter_instance = RedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Pesana log pengujian",
        args=(),
        exc_info=None,
    )
    # Tambahkan atribut sensitif
    record.text = "Isi dokumen sangat rahasia"
    record.question = "Berapa saldo tabungan saya?"
    record.answer = "Saldo tabungan adalah Rp 50.000.000"

    assert filter_instance.filter(record) is True
    assert record.text == "[REDACTED]"
    assert record.question == "[REDACTED]"
    assert record.answer == "[REDACTED]"


def test_redaction_filter_preserves_attributes_when_log_content_true(monkeypatch):
    """Memastikan atribut dipertahankan jika LOG_CONTENT=True."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LOG_CONTENT", True)

    filter_instance = RedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Pesan log pengujian",
        args=(),
        exc_info=None,
    )
    record.text = "Teks asli yang boleh dicatat"

    assert filter_instance.filter(record) is True
    assert record.text == "Teks asli yang boleh dicatat"
