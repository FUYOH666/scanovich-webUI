"""Extract JSON object from model text (fences or raw)."""

from __future__ import annotations

import json
import re
from typing import Any

from gpthub_orchestrator.pptx.schema import MAX_SLIDES, SlidePlan, SlideSpec, normalize_slide_kind

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
    return SlidePlan.model_validate({"slides": normalized})


def parse_slide_plan_text(model_text: str) -> SlidePlan:
    fragment = extract_json_object(model_text)
    data = json.loads(fragment)
    if not isinstance(data, dict):
        raise ValueError("json_not_object")
    plan = slide_plan_from_parsed_dict(data)
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
