"""PDF ingest extraction."""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from gpthub_orchestrator.ingest.pdf_extract import PdfExtractError, parse_pdf_bytes

_FIXTURE_LLM_SOFTWARE_ENG_PDF = (
    Path(__file__).resolve().parent
    / "sources"
    / "Large_Language_Model-Based_Agents_for_Software_Eng.pdf"
)


def test_parse_pdf_blank_page_returns_ocr_placeholder():
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    buf = BytesIO()
    w.write(buf)
    text = parse_pdf_bytes(buf.getvalue(), max_bytes=1_000_000, max_pages=10)
    assert "OCR" in text or "empty" in text.lower()


def test_parse_pdf_rejects_oversized():
    with pytest.raises(PdfExtractError, match="max_bytes"):
        parse_pdf_bytes(b"x" * 5000, max_bytes=1000, max_pages=1)


def test_parse_pdf_rejects_garbage():
    with pytest.raises(PdfExtractError):
        parse_pdf_bytes(b"not-a-pdf", max_bytes=10000, max_pages=1)


def test_parse_pdf_fixture_llm_agents_software_eng_paper():
    """Real ACM-style PDF under tests/sources/ (same limits as default ingest settings)."""
    if not _FIXTURE_LLM_SOFTWARE_ENG_PDF.is_file():
        pytest.skip(f"missing fixture: {_FIXTURE_LLM_SOFTWARE_ENG_PDF}")
    raw = _FIXTURE_LLM_SOFTWARE_ENG_PDF.read_bytes()
    text = parse_pdf_bytes(raw, max_bytes=15_000_000, max_pages=50)
    assert len(text) > 500
    low = text.lower()
    assert "large" in low and "language" in low
    assert "software" in low
