"""Infer ``pptx_plan_audience`` from recent user wording (no LLM call).

Used so slide-plan prompts and template match the latest user intent when the
phrase clearly signals an audience; otherwise ``default_audience`` (env) applies.
"""

from __future__ import annotations

import re
from typing import Any, Final

from gpthub_orchestrator.pptx.audience_templates import (
    PPTX_PLAN_AUDIENCE_VALUES,
    normalize_pptx_plan_audience,
)

# First match wins; put more specific cues before broader ones.
_AUDIENCE_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    (
        "investor",
        r"инвестор|investor|венчур|venture|\bvc\b|"
        r"для\s+инвестор|инвесторам|shareholder|акционер",
    ),
    (
        "education",
        r"студент|школьник|учебн|образован|лекци|преподават|"
        r"школ|университет|university|\bedu\b|school\b|tutorial|тренинг\s+для",
    ),
    (
        "creative",
        r"креатив|творческ|дизайнер|creative\b|portfolio|портфолио|"
        r"художник|арт-дирек",
    ),
    (
        "business",
        r"бизнес|corporate|\bb2b\b|руководств|стейкхолдер|stakeholder|"
        r"делов(ое|ой|ая)|коммерч",
    ),
    (
        "general",
        r"широк(ая|ой|ий|ому)\s+аудитори|mass\s+market|для\s+всех|широк(ий|ая|ого)\s+круг",
    ),
)


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
        return " ".join(parts)
    return ""


def _last_user_texts(messages: list[dict[str, Any]], *, last_n: int) -> list[str]:
    out: list[str] = []
    for m in messages:
        if str(m.get("role", "")).lower() != "user":
            continue
        t = _message_content_text(m.get("content")).strip()
        if t:
            out.append(t)
    return out[-last_n:] if last_n > 0 else out


def infer_pptx_plan_audience_from_messages(
    messages: list[dict[str, Any]],
    *,
    last_user_messages: int = 4,
) -> str | None:
    """Return an audience key if recent user text matches; else ``None``."""
    texts = _last_user_texts(messages, last_n=last_user_messages)
    if not texts:
        return None
    blob = "\n".join(texts).lower()
    for key, pattern in _AUDIENCE_PATTERNS:
        if key not in PPTX_PLAN_AUDIENCE_VALUES or key == "auto":
            continue
        if re.search(pattern, blob, re.IGNORECASE):
            return key
    return None


def resolve_effective_pptx_plan_audience(
    messages: list[dict[str, Any]],
    *,
    default_audience: str,
    last_user_messages: int = 4,
) -> str:
    """Infer from messages, else normalized ``default_audience`` (e.g. from Settings)."""
    got = infer_pptx_plan_audience_from_messages(
        messages,
        last_user_messages=last_user_messages,
    )
    if got is not None:
        return got
    return normalize_pptx_plan_audience(default_audience)
