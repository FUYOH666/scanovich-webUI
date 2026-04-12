"""Rich document conversion via markitdown (DOCX, XLSX, PPTX, etc.)."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# MIME types and extensions handled by markitdown.
# We keep this explicit so the pipeline can route cleanly.
_RICHDOC_MIMES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
        "application/msword",  # .doc (legacy)
        "application/vnd.ms-excel",  # .xls (legacy)
        "application/vnd.ms-powerpoint",  # .ppt (legacy)
        "application/rtf",
        "application/epub+zip",
    }
)

_RICHDOC_SUFFIXES = (
    ".docx",
    ".xlsx",
    ".pptx",
    ".doc",
    ".xls",
    ".ppt",
    ".rtf",
    ".epub",
)


def is_richdoc_item(mime: str, filename: str) -> bool:
    """True if this file should be converted via markitdown."""
    if mime in _RICHDOC_MIMES:
        return True
    return filename.lower().endswith(_RICHDOC_SUFFIXES)


class RichDocConvertError(Exception):
    pass


def convert_richdoc_bytes(data: bytes, *, filename: str) -> str:
    """Convert raw bytes of a rich document to markdown text.

    Uses markitdown (from Microsoft) which supports DOCX, XLSX, PPTX,
    DOC, XLS, PPT, RTF, EPUB, and more.

    Raises :class:`RichDocConvertError` on any failure.
    """
    try:
        from markitdown import MarkItDown  # type: ignore[import-not-found]
    except ImportError as e:
        raise RichDocConvertError("markitdown not installed") from e

    md = MarkItDown()
    try:
        result = md.convert_stream(io.BytesIO(data), file_extension=_ext(filename))
    except Exception as e:  # noqa: BLE001
        raise RichDocConvertError(f"convert_failed: {type(e).__name__}: {e}") from e
    text = getattr(result, "text_content", "") or ""
    if not text.strip():
        raise RichDocConvertError("empty_output")
    return text


def _ext(filename: str) -> str:
    """Extract extension including the dot, e.g. '.docx'."""
    low = filename.lower()
    for s in _RICHDOC_SUFFIXES:
        if low.endswith(s):
            return s
    # Fallback: last dot-part.
    dot = low.rfind(".")
    if dot >= 0:
        return low[dot:]
    return ""
