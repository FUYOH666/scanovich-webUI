"""Extract JSON object from model text (fences or raw)."""

from __future__ import annotations

import json
import re
from typing import Any

from gpthub_orchestrator.pptx.schema import MAX_SLIDES, SlidePlan

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
