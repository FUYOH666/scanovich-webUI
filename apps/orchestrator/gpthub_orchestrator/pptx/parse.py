"""Extract JSON object from model text (fences or raw)."""

from __future__ import annotations

import json
import re
from typing import Any

from gpthub_orchestrator.pptx.schema import MAX_SLIDES, SlidePlan, SlideSpec, normalize_slide_kind

# Parallel slide agents: hard cap on visible text (title + bullet strings) after LLM output.
SLIDE_AGENT_MAX_VISIBLE_CHARS = 500


def _visible_char_len(title: str, bullets: list[str]) -> int:
    return len(title) + sum(len(b) for b in bullets)


def _truncate_line_at_word_boundary(line: str, max_chars: int) -> str:
    """Shorten a single line without splitting mid-word when possible."""
    if max_chars <= 0:
        return ""
    if len(line) <= max_chars:
        return line
    prefix = line[:max_chars]
    last_space = prefix.rfind(" ")
    if last_space > 0:
        return prefix[:last_space]
    # One long token (URL, etc.): no clean word break — keep a prefix up to the cap.
    return prefix


def _truncate_text_respecting_lines(text: str, max_chars: int) -> str:
    """Trim to max_chars: drop whole lines from the end; last line only trimmed at word end, not mid-line."""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    if len(lines) == 1:
        return _truncate_line_at_word_boundary(lines[0], max_chars)

    acc: list[str] = []
    used = 0
    for i, line in enumerate(lines):
        sep = 0 if i == 0 else 1
        if i == 0:
            if len(line) <= max_chars:
                acc.append(line)
                used = len(line)
            else:
                return _truncate_line_at_word_boundary(line, max_chars)
        else:
            needed = sep + len(line)
            if used + needed <= max_chars:
                acc.append(line)
                used += needed
            else:
                break
    return "\n".join(acc)


def clamp_slide_visible_to_max(
    spec: SlideSpec,
    *,
    max_chars: int = SLIDE_AGENT_MAX_VISIBLE_CHARS,
) -> SlideSpec:
    """Drop whole bullets from the end, then trim remaining text at line/word boundaries.

    Never slices arbitrary substrings mid-line except as a last resort for a single token
    without spaces. Speaker notes and kind are unchanged.
    """
    title = spec.title
    bullets = list(spec.bullets)

    while len(bullets) > 1 and _visible_char_len(title, bullets) > max_chars:
        bullets.pop()

    if _visible_char_len(title, bullets) <= max_chars:
        return SlideSpec(title=title, bullets=bullets, notes=spec.notes, kind=spec.kind)

    if not bullets:
        return SlideSpec(
            title=_truncate_text_respecting_lines(title, max_chars),
            bullets=[],
            notes=spec.notes,
            kind=spec.kind,
        )

    budget = max_chars - len(title)
    if budget <= 0:
        return SlideSpec(
            title=_truncate_text_respecting_lines(title, max_chars),
            bullets=[],
            notes=spec.notes,
            kind=spec.kind,
        )
    return SlideSpec(
        title=title,
        bullets=[_truncate_text_respecting_lines(bullets[0], budget)],
        notes=spec.notes,
        kind=spec.kind,
    )

_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def extract_json_object(text: str) -> str:
    s = text.strip()
    m = _FENCE.search(s)
    if m:
        s = m.group(1).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no_json_object")
    return s[start : end + 1]


def slide_plan_from_parsed_dict(data: dict[str, Any]) -> SlidePlan:
    slides_raw = data.get("slides")
    if not isinstance(slides_raw, list):
        slides_raw = []
    normalized: list[dict[str, Any]] = []
    for item in slides_raw[:MAX_SLIDES]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": item.get("title", ""),
                "bullets": item.get("bullets"),
                "notes": item.get("notes", ""),
                "kind": normalize_slide_kind(item.get("kind")),
            }
        )
    pt = data.get("presentation_title")
    payload: dict[str, Any] = {"slides": normalized}
    if pt is not None and str(pt).strip():
        payload["presentation_title"] = str(pt).strip()
    return SlidePlan.model_validate(payload)


def parse_slide_plan_text(model_text: str) -> SlidePlan:
    fragment = extract_json_object(model_text)
    data = json.loads(fragment)
    if not isinstance(data, dict):
        raise ValueError("json_not_object")
    plan = slide_plan_from_parsed_dict(data)
    if not (plan.presentation_title or "").strip():
        raise ValueError("missing_presentation_title")
    if not plan.slides:
        raise ValueError("empty_slides")
    return plan


def parse_outline_plan_text(model_text: str) -> SlidePlan:
    """Outline step: titles (+ optional kind); bullets/notes omitted or empty."""
    fragment = extract_json_object(model_text)
    data = json.loads(fragment)
    if not isinstance(data, dict):
        raise ValueError("json_not_object")
    plan = slide_plan_from_parsed_dict(data)
    if not (plan.presentation_title or "").strip():
        raise ValueError("missing_presentation_title")
    if not plan.slides:
        raise ValueError("empty_slides")
    for s in plan.slides:
        if not (s.title or "").strip():
            raise ValueError("outline_empty_title")
    return plan


def parse_single_slide_detail_text(model_text: str) -> dict[str, Any]:
    """One-slide JSON object or {slides:[one]}."""
    fragment = extract_json_object(model_text)
    data = json.loads(fragment)
    if not isinstance(data, dict):
        raise ValueError("json_not_object")
    if "slides" in data:
        items = data.get("slides")
        if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict):
            data = items[0]
        elif isinstance(items, list) and len(items) > 1:
            raise ValueError("multi_slide_in_detail")
        else:
            raise ValueError("bad_slides_array")
    return data


def slide_spec_from_agent_payload(
    payload: dict[str, Any],
    *,
    title_fallback: str,
    kind_fallback: str | None,
) -> SlideSpec:
    raw_kind = payload.get("kind")
    if raw_kind is None or raw_kind == "":
        raw_kind = kind_fallback
    merged: dict[str, Any] = {
        "title": (str(payload.get("title", "")).strip() or title_fallback).strip(),
        "bullets": payload.get("bullets"),
        "notes": payload.get("notes", "") or "",
        "kind": raw_kind,
    }
    return SlideSpec.model_validate(merged)
