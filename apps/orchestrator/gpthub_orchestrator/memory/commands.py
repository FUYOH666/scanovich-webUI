"""Parse user-facing memory commands out of plain text.

We intentionally keep this a pure-function, dependency-free module so it can
be unit-tested without touching sqlite or the MWS API.

Supported intents:
  - remember:    «запомни, что я ...», «запомни X», «remember that ...», «/remember ...»
  - forget:      «забудь про X», «забудь всё», «forget X», «/forget X»
  - recall_all:  «что ты обо мне помнишь?», «what do you remember?», «/memories»

The parser returns a `MemoryCommand` dataclass; if no command matches, returns
None and the caller proceeds with normal chat routing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CommandKind = Literal["remember", "forget", "forget_all", "recall_all"]


@dataclass
class MemoryCommand:
    kind: CommandKind
    payload: str  # the fact to remember / substring to forget (empty for recall/forget_all)


# ---------------------------------------------------------------------------
# Remember
# ---------------------------------------------------------------------------

_REMEMBER_PATTERNS = [
    re.compile(
        r"^\s*запомни(?:[,\s]+(?:пожалуйста|plz|please))?"
        r"(?:[,\s]+что)?[:\s,-]+(?P<p>.+)$",
        re.IGNORECASE | re.UNICODE | re.DOTALL,
    ),
    re.compile(
        r"^\s*remember(?:[,\s]+(?:please|plz))?"
        r"(?:[,\s]+that)?[:\s,-]+(?P<p>.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"^\s*/remember\s+(?P<p>.+)$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*/remember_this\s+(?P<p>.+)$", re.IGNORECASE | re.DOTALL),
]

# ---------------------------------------------------------------------------
# Forget
# ---------------------------------------------------------------------------

_FORGET_ALL_PATTERNS = [
    re.compile(r"^\s*забудь\s+(?:всё|все|всё\s+обо\s+мне|все\s+обо\s+мне)\s*[.!?]*\s*$", re.IGNORECASE | re.UNICODE),
    re.compile(r"^\s*forget\s+(?:everything|all|all\s+about\s+me)\s*[.!?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*/forget_all\s*$", re.IGNORECASE),
]

_FORGET_PATTERNS = [
    re.compile(
        r"^\s*забудь(?:\s+(?:про|о|об))?[:\s,-]+(?P<p>.+)$",
        re.IGNORECASE | re.UNICODE | re.DOTALL,
    ),
    re.compile(
        r"^\s*forget(?:\s+(?:about|that))?[:\s,-]+(?P<p>.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"^\s*/forget\s+(?P<p>.+)$", re.IGNORECASE | re.DOTALL),
]

# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------

_RECALL_ALL_PATTERNS = [
    re.compile(
        r"^\s*что\s+ты\s+(?:обо\s+мне\s+)?помнишь\s*[?.!]*\s*$",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"^\s*что\s+ты\s+знаешь\s+обо\s+мне\s*[?.!]*\s*$",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"^\s*what\s+do\s+you\s+(?:remember|know)(?:\s+about\s+me)?\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*/memories\s*$", re.IGNORECASE),
    re.compile(r"^\s*/memory\s*$", re.IGNORECASE),
]


def parse_memory_command(text: str) -> MemoryCommand | None:
    if not text:
        return None
    s = text.strip()
    if not s:
        return None
    # Cap: don't hijack long essays.
    if len(s) > 4000:
        return None

    for pat in _RECALL_ALL_PATTERNS:
        if pat.match(s):
            return MemoryCommand(kind="recall_all", payload="")

    for pat in _FORGET_ALL_PATTERNS:
        if pat.match(s):
            return MemoryCommand(kind="forget_all", payload="")

    for pat in _FORGET_PATTERNS:
        m = pat.match(s)
        if m:
            p = m.group("p").strip(" .!?:;,-—")
            if p:
                return MemoryCommand(kind="forget", payload=p)

    for pat in _REMEMBER_PATTERNS:
        m = pat.match(s)
        if m:
            p = m.group("p").strip(" .!?:;,-—")
            if p:
                return MemoryCommand(kind="remember", payload=p)

    return None
