"""PPTX **intent** helpers for the heuristic classifier.

The full pipeline (slide plan via LiteLLM, ``python-pptx`` build, artifacts) lives in
the ``gpthub_orchestrator.pptx`` package and ``main.py`` short-circuit — not here.

This module stays small and import-safe (used from ``classifier`` via lazy import)
to avoid circular imports with the rest of the orchestrator.
"""

from __future__ import annotations

import re

from gpthub_orchestrator.classifier import RU_IMPERATIVE_CREATE_VERBS

# ---------------------------------------------------------------------------
# Slash commands always win.
# ---------------------------------------------------------------------------
_SLASH_PPTX = re.compile(r"(?:^|\s)/(?:pptx|slides|deck|presentation)\b", re.IGNORECASE)

_PPTX_PHRASES = [
    # RU verbs that almost always mean "make a deck".
    re.compile(
        r"\b(?:сделай|создай|сгенерир\w*|подготов\w*|собер[иь]|построй|нарису\w*)"
        r"[^.?!\n]{0,40}\bпрезентац\w*",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        rf"\bпрезентац\w*\b[^.?!\n]{{0,50}}\b(?:{RU_IMPERATIVE_CREATE_VERBS})\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(r"\bпрезентац\w*\b[^.?!\n]{0,30}\b(?:по|про|о|об|на\s+тему)\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\bслайд\w*\s+(?:по|про|о|об|на\s+тему)\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\bколод\w*\s+слайд\w*\b", re.IGNORECASE | re.UNICODE),
    # RU "в формате pptx" / "формат pptx" / "в pptx".
    re.compile(r"\bв\s+(?:формате?\s+)?pptx\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\bформат\w*\s+pptx\b", re.IGNORECASE | re.UNICODE),
    # EN.
    re.compile(
        r"\b(?:make|build|create|generate|draft|prepare)\s+"
        r"(?:an?\s+|the\s+)?(?:presentation|deck|slides|slide\s+deck|powerpoint|pptx)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bslide\s+deck\s+(?:on|about|for)\b", re.IGNORECASE),
    re.compile(r"\b(?:powerpoint|pptx)\s+(?:on|about|for)\b", re.IGNORECASE),
]


def is_pptx_request(text: str) -> bool:
    """True if the last user text should be treated as PPTX intent (classifier hint)."""
    if not text:
        return False
    s = text.strip()
    if not s:
        return False
    # Hard ceiling: don't hijack a giant document paste into PPTX.
    if len(s) > 8000:
        return False
    if _SLASH_PPTX.search(s):
        return True
    for pat in _PPTX_PHRASES:
        if pat.search(s):
            return True
    return False


def extract_pptx_topic(text: str) -> str:
    """Strip a leading slash command. Return the original text otherwise.

    The plan model receives the full conversation in production; this helper is
    only for callers that need a topic line without the ``/pptx`` prefix.
    """
    s = text.strip()
    m = _SLASH_PPTX.search(s)
    if m and m.start() <= 1:
        return s[m.end() :].strip(" :—-")
    return s
