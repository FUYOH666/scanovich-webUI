"""PDF ingest extraction."""

from io import BytesIO

import pytest
from pypdf import PdfWriter

from gpthub_orchestrator.ingest.pdf_extract import PdfExtractError, parse_pdf_bytes


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
