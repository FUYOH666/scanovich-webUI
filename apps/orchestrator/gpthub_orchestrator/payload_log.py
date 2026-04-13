"""Sanitize and log incoming chat `messages` for debugging WebUI → orchestrator payloads."""

from __future__ import annotations

import json
import logging
from typing import Any

# Cap single log line size (sanitized JSON).
_MAX_JSON_CHARS = 120_000


def sanitize_for_log(
    obj: Any,
    *,
    content_str_clip: int = 16_000,
    url_len_threshold: int = 600,
    _depth: int = 0,
) -> Any:
    """Redact huge / binary URLs; clip very long strings (Open WebUI RAG can send novels)."""
    if _depth > 24:
        return "<max_depth>"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        if obj.startswith("data:") or len(obj) > url_len_threshold:
            return f"<redacted str len={len(obj)}>"
        if len(obj) > content_str_clip:
            return obj[: content_str_clip - 24] + f"... <truncated {len(obj)} chars>"
        return obj
    if isinstance(obj, list):
        return [
            sanitize_for_log(x, content_str_clip=content_str_clip, url_len_threshold=url_len_threshold, _depth=_depth + 1)
            for x in obj
        ]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in ("url", "detail", "b64_json") and isinstance(v, str) and (
                v.startswith("data:") or len(v) > url_len_threshold
            ):
                out[k] = f"<redacted str len={len(v)}>"
            elif k == "image_url" and isinstance(v, dict):
                out[k] = sanitize_for_log(v, content_str_clip=content_str_clip, url_len_threshold=url_len_threshold, _depth=_depth + 1)
            else:
                out[k] = sanitize_for_log(v, content_str_clip=content_str_clip, url_len_threshold=url_len_threshold, _depth=_depth + 1)
        return out
    return str(obj)


def log_chat_messages(
    log: logging.Logger,
    phase: str,
    messages: list[dict[str, Any]],
) -> None:
    try:
        sanitized = sanitize_for_log(messages)
        text = json.dumps({"phase": phase, "messages": sanitized}, ensure_ascii=False)
        if len(text) > _MAX_JSON_CHARS:
            text = text[: _MAX_JSON_CHARS - 48] + f"... <json truncated total_len={len(text)}>"
        log.info("incoming_chat_messages %s", text)
    except Exception as e:  # noqa: BLE001
        log.warning("incoming_chat_messages_log_failed phase=%s err=%s", phase, e)
