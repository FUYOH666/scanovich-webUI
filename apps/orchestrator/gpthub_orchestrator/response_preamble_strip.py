"""Last-resort removal of known chain-of-thought preambles from assistant text (non-stream only)."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Substrings that must not appear in user-visible assistant text (regression tests import this).
BAD_LEAK_SUBSTRINGS = (
    "thinking process",
    "analyze user input",
    "check constraints",
    "final output",
    "self-correction",
    "constraint 1",
    "constraint 2",
    "here's a thinking process",
    "here is a thinking process",
)

_THINKING_HEAD = re.compile(
    r"^(here'?s a thinking process|here is a thinking process)\s*:?\s*",
    re.IGNORECASE | re.MULTILINE,
)


def strip_known_cot_preamble(text: str) -> tuple[str, bool]:
    """
    Remove a leading CoT-style block when it matches known patterns.
    Returns (new_text, whether modification was applied).
    """
    if not text or not text.strip():
        return text, False
    original = text
    m = _THINKING_HEAD.match(text)
    if m:
        rest = text[m.end() :]
        para = rest.split("\n\n", 1)
        if len(para) == 2:
            text = para[1].lstrip()
        else:
            lines = rest.splitlines()
            idx = 0
            while idx < len(lines) and lines[idx].strip() == "":
                idx += 1
            while idx < len(lines):
                line_lower = lines[idx].lower().strip()
                if any(
                    line_lower.startswith(p)
                    for p in (
                        "analyze ",
                        "check ",
                        "constraint",
                        "formulate",
                        "language:",
                        "intent:",
                        "mode:",
                    )
                ):
                    idx += 1
                    continue
                break
            text = "\n".join(lines[idx:]).lstrip()
        if text != original:
            logger.info("preamble_strip_applied kind=thinking_head")
            return text, True

    lines = text.splitlines()
    drop = 0
    while drop < len(lines):
        s = lines[drop].strip().lower()
        if s == "":
            drop += 1
            continue
        if any(
            s.startswith(p)
            for p in (
                "analyze user input",
                "check constraints",
                "final output",
                "self-correction",
            )
        ):
            drop += 1
            continue
        break
    if drop > 0:
        text = "\n".join(lines[drop:]).lstrip()
        logger.info("preamble_strip_applied kind=leading_lines dropped=%s", drop)
        return text, True
    return text, False


def assistant_content_has_leak_substrings(text: str) -> list[str]:
    """Return which BAD_LEAK_SUBSTRINGS appear in text (lowercase compare)."""
    low = text.lower()
    return [s for s in BAD_LEAK_SUBSTRINGS if s in low]
