"""Remove provider reasoning metadata from OpenAI-style completions (client-facing contract)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Keys that upstream providers may add beside visible content.
REASONING_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "reasoning",
        "reasoning_content",
        "reasoning_details",
        "thinking",
        "thinking_blocks",
        "thought",
    }
)


def _strip_reasoning_keys(d: dict[str, Any]) -> int:
    removed = 0
    for k in list(d.keys()):
        if k in REASONING_PAYLOAD_KEYS:
            d.pop(k, None)
            removed += 1
    return removed


def strip_reasoning_from_completion_payload(payload: dict[str, Any]) -> None:
    """In-place: drop reasoning* fields from choices and optional root (non-stream JSON)."""
    total = _strip_reasoning_keys(payload)
    choices = payload.get("choices")
    if not isinstance(choices, list):
        if total:
            logger.info("reasoning_fields_stripped_from_completion root_only=%s", total)
        return
    for ch in choices:
        if not isinstance(ch, dict):
            continue
        total += _strip_reasoning_keys(ch)
        msg = ch.get("message")
        if isinstance(msg, dict):
            total += _strip_reasoning_keys(msg)
        delta = ch.get("delta")
        if isinstance(delta, dict):
            total += _strip_reasoning_keys(delta)
    if total:
        logger.info("reasoning_fields_stripped_from_completion total=%s", total)


def strip_reasoning_from_stream_chunk(obj: dict[str, Any]) -> None:
    """In-place: same as completion but for one SSE JSON object."""
    strip_reasoning_from_completion_payload(obj)


def filter_sse_data_line_json(line: str, *, strip_enabled: bool) -> str:
    """
    If line is ``data: <json>``, parse and strip reasoning keys; return full line (no trailing newline).
    Non-JSON lines and ``data: [DONE]`` unchanged.
    """
    if not strip_enabled or not line.startswith("data: "):
        return line
    rest = line[6:].strip()
    if rest == "[DONE]":
        return line
    try:
        obj = json.loads(rest)
    except json.JSONDecodeError:
        return line
    if not isinstance(obj, dict):
        return line
    strip_reasoning_from_stream_chunk(obj)
    return "data: " + json.dumps(obj, ensure_ascii=False)


def merge_reasoning_exclude_into_body(body: dict[str, Any], *, enabled: bool) -> None:
    """Ask the upstream provider not to return reasoning tokens when supported."""
    if not enabled:
        return
    existing = body.get("reasoning")
    if isinstance(existing, dict):
        merged: dict[str, Any] = {**existing, "exclude": True}
    else:
        merged = {"exclude": True}
    body["reasoning"] = merged
