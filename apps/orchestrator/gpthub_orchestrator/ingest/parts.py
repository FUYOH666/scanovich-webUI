"""Extract file/audio work items from the last user message (OpenAI-style content parts)."""

from __future__ import annotations

import base64
import binascii
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_DATA_URL = re.compile(
    r"^data:(?P<mime>[\w/+.\-]+);base64,(?P<b64>.+)$",
    re.DOTALL,
)


@dataclass
class FileWorkItem:
    filename: str
    mime: str
    raw: bytes


def _decode_data_url(url: str) -> tuple[str, bytes] | None:
    m = _DATA_URL.match(url.strip())
    if not m:
        return None
    mime = m.group("mime").lower()
    b64 = m.group("b64").strip()
    try:
        raw = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        return None
    return mime, raw


def _part_file_payload(part: dict[str, Any]) -> FileWorkItem | None:
    fobj = part.get("file")
    if not isinstance(fobj, dict):
        return None
    fn = str(fobj.get("filename") or "attachment").strip() or "attachment"
    fd = fobj.get("file_data")
    if not isinstance(fd, str):
        return None
    decoded = _decode_data_url(fd)
    if not decoded:
        return None
    mime, raw = decoded
    return FileWorkItem(filename=fn, mime=mime, raw=raw)


def work_item_from_part(part: dict[str, Any]) -> FileWorkItem | None:
    ptype = str(part.get("type") or "").lower()
    if ptype == "file":
        return _part_file_payload(part)
    if ptype in ("input_audio", "audio"):
        return _part_input_audio(part)
    return None


def _part_input_audio(part: dict[str, Any]) -> FileWorkItem | None:
    """OpenAI-style input_audio with base64 or data URL."""
    ia = part.get("input_audio")
    if not isinstance(ia, dict):
        return None
    data = ia.get("data")
    if isinstance(data, str):
        dec = _decode_data_url(data)
        if dec:
            mime, raw = dec
            fn = str(ia.get("filename") or "audio").strip() or "audio"
            return FileWorkItem(filename=fn, mime=mime, raw=raw)
    b64 = ia.get("base64")
    if isinstance(b64, str):
        try:
            raw = base64.b64decode(b64.strip(), validate=False)
        except (binascii.Error, ValueError):
            return None
        fmt = str(ia.get("format") or "wav").lower()
        mime = f"audio/{fmt}" if "/" not in fmt else fmt
        fn = str(ia.get("filename") or f"audio.{fmt}").strip() or "audio"
        return FileWorkItem(filename=fn, mime=mime, raw=raw)
    return None


def last_user_message_index(messages: list[dict[str, Any]]) -> int | None:
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user":
            return i
    return None


def extract_file_work_items(
    messages: list[dict[str, Any]],
) -> tuple[int | None, list[tuple[int, FileWorkItem]]]:
    """Indices of PDF/audio parts in the last user message + work items."""
    idx = last_user_message_index(messages)
    if idx is None:
        return None, []
    msg = messages[idx]
    content = msg.get("content")
    if not isinstance(content, list):
        return idx, []
    found: list[tuple[int, FileWorkItem]] = []
    for i, part in enumerate(content):
        if not isinstance(part, dict):
            continue
        w = work_item_from_part(part)
        if w:
            found.append((i, w))
    return idx, found


def strip_content_indices(messages: list[dict[str, Any]], user_idx: int, drop_indices: set[int]) -> None:
    """Remove listed part indices from user message content (mutates)."""
    msg = messages[user_idx]
    content = msg.get("content")
    if not isinstance(content, list):
        return
    new_parts = [p for j, p in enumerate(content) if j not in drop_indices]
    if len(new_parts) == 1 and isinstance(new_parts[0], dict) and new_parts[0].get("type") == "text":
        msg["content"] = str(new_parts[0].get("text") or "")
    elif not new_parts:
        msg["content"] = ""
    else:
        msg["content"] = new_parts
