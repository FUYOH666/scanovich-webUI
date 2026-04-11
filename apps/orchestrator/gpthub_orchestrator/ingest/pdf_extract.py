"""Extract plain text from PDF bytes (bounded)."""

from __future__ import annotations

import logging
from io import BytesIO

from pypdf import PdfReader

logger = logging.getLogger(__name__)


class PdfExtractError(Exception):
    pass


def parse_pdf_bytes(
    data: bytes,
    *,
    max_bytes: int,
    max_pages: int,
) -> str:
    if len(data) > max_bytes:
        raise PdfExtractError(f"pdf exceeds max_bytes ({max_bytes})")
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as e:
        logger.warning("pdf_reader_failed err=%s", e)
        raise PdfExtractError("invalid_pdf") from e
    texts: list[str] = []
    n = min(len(reader.pages), max_pages)
    for i in range(n):
        try:
            t = reader.pages[i].extract_text() or ""
        except Exception as e:
            logger.warning("pdf_page_extract_failed page=%s err=%s", i, e)
            t = ""
        texts.append(t)
    joined = "\n\n".join(texts).strip()
    if not joined:
        return "[empty or non-text PDF - OCR not enabled in this baseline]"
    return joined
