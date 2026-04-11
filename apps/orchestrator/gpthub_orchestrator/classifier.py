"""Modality / task hints from OpenAI-style chat messages (rule-based v1)."""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Short acknowledgments / goodbyes stay on the light chat chain.
_ACK_PHRASES = frozenset(
    {
        "thanks",
        "thank you",
        "thx",
        "ty",
        "ok",
        "okay",
        "да",
        "нет",
        "yes",
        "no",
        "спасибо",
        "мерси",
        "понял",
        "понятно",
        "bye",
        "пока",
    }
)

_GREETING_START = re.compile(
    r"^\s*(?:"
    r"(?:привет|здравствуй(?:те)?|доброе\s+утро|добрый\s+(?:день|вечер|утро)|хай|салют)"
    r"(?:[,\s!.…]|$)|"
    r"(?:\bhi\b|\bhello\b|\bhey\b|howdy|greetings)"
    r"(?:[,\s!.…]|$)|"
    r"good\s+(?:morning|evening|afternoon|day)\b"
    r")",
    re.IGNORECASE | re.UNICODE,
)

# Whole-message casual check-ins (short only) → canned / fast_text_chat path
_CASUAL_SMALL_TALK_ONLY = re.compile(
    r"^\s*(?:"
    r"как\s+дела\b\s*[?.!…]*\s*|"
    r"как\s+ты\b\s*[?.!…]*\s*|"
    r"что\s+нового\b\s*[?.!…]*\s*|"
    r"ты\s+тут\b\s*[?.!…]*\s*|"
    r"how\s+are\s+you\b\s*[?.!…]*\s*|"
    r"what'?s\s+up\b\s*[?.!…]*\s*|"
    r"how'?s\s+it\s+going\b\s*[?.!…]*\s*"
    r")$",
    re.IGNORECASE | re.UNICODE,
)

# Date/time / calendar questions — canned short-circuit cannot answer these
_SUBSTANTIVE_FACTUAL_QUESTION = re.compile(
    r"какой\s+(сегодня\s+)?(день|день\s+недели|число|месяц|год)\b|"
    r"какое\s+(сегодня\s+)?(число|время)\b|"
    r"какая\s+(сегодня\s+)?дата\b|"
    r"который\s+час\b|"
    r"сколько\s+времени\b|"
    r"what\s+day\b|"
    r"what'?s\s+the\s+(date|time)\b|"
    r"what\s+(is\s+)?the\s+date\b|"
    r"what\s+time\b|"
    r"which\s+day\b",
    re.IGNORECASE | re.UNICODE,
)


def _is_greeting_or_tiny(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    # Greeting prefix + real question → not tiny (canned would ignore the question)
    if "?" in s:
        m = _GREETING_START.match(s)
        if m:
            if _SUBSTANTIVE_FACTUAL_QUESTION.search(s):
                return False
            tail = s[m.end() :].strip()
            if tail and len(tail) > 12 and "?" in tail:
                return False
    if s.lower().rstrip("!.… ") in _ACK_PHRASES:
        return True
    if len(s) <= 80 and bool(_CASUAL_SMALL_TALK_ONLY.match(s)):
        return True
    if len(s) > 96:
        return False
    return bool(_GREETING_START.match(s))


class TaskType(str, Enum):
    SIMPLE_CHAT = "simple_chat"
    GREETING_OR_TINY = "greeting_or_tiny"
    CODE_HELP = "code_help"
    FILE_ANALYSIS = "file_analysis"
    SUMMARIZATION = "summarization"
    IMAGE_ANALYSIS = "image_analysis"
    AUDIO_ANALYSIS = "audio_analysis"
    MULTIMODAL_WORKFLOW = "multimodal_workflow"
    DEEP_RESEARCH = "deep_research"


def _flatten_text(parts: list[dict[str, Any]] | str) -> str:
    if isinstance(parts, str):
        return parts
    chunks: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "text":
            chunks.append(str(p.get("text", "")))
    return " ".join(chunks)


def _message_text(m: dict[str, Any]) -> str:
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return _flatten_text(c)
    return ""


def _has_image_part(content: Any) -> bool:
    if isinstance(content, list):
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "image_url":
                return True
            if p.get("type") == "image":
                return True
    return False


def classify_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Return modalities, task_type, complexity_hint for trace + router."""
    has_image = any(_has_image_part(m.get("content")) for m in messages)
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = _message_text(m)
            break

    lower = last_user.lower()
    code_hints = any(
        x in lower
        for x in (
            "traceback",
            "exception",
            "async def",
            "def ",
            "import ",
            "typescript",
            "javascript",
            "fastapi",
            "docker",
        )
    )
    analyze_hints = any(x in lower for x in ("analyze", "compare", "architecture", "debug", "анализ", "сравни"))
    doc_hints = any(
        x in lower
        for x in (
            "summarize",
            "summary",
            "tl;dr",
            "pdf",
            "document",
            "docx",
            "whitepaper",
            "суммариз",
            "документ",
            "конспект",
        )
    )
    long_text = len(last_user) > 6000

    modalities: list[str] = ["text"]
    if has_image:
        modalities.append("image")

    # Deep research / Expert Council wins over everything except multimodal.
    # We lazy-import here to avoid a classifier↔council import cycle.
    deep_research_hit = False
    if not has_image:
        from gpthub_orchestrator.council import is_council_request  # local import to avoid cycle

        deep_research_hit = is_council_request(last_user)

    if has_image and (analyze_hints or code_hints):
        task = TaskType.MULTIMODAL_WORKFLOW
    elif has_image:
        task = TaskType.IMAGE_ANALYSIS
    elif deep_research_hit:
        task = TaskType.DEEP_RESEARCH
    elif (doc_hints or long_text) and not has_image:
        task = TaskType.SUMMARIZATION if doc_hints else TaskType.FILE_ANALYSIS
    elif code_hints or analyze_hints:
        task = TaskType.CODE_HELP
    elif not has_image and _is_greeting_or_tiny(last_user):
        task = TaskType.GREETING_OR_TINY
    else:
        task = TaskType.SIMPLE_CHAT

    complexity = 0
    if len(modalities) > 1 or (has_image and analyze_hints):
        complexity += 2
    if code_hints:
        complexity += 1
    if analyze_hints:
        complexity += 1

    out = {
        "modalities": modalities,
        "task_type": task.value,
        "complexity_score": complexity,
        "user_text_preview": last_user[:200],
    }
    logger.info(
        "modality_classified",
        extra={"extra": json.dumps(out, ensure_ascii=False)},
    )
    return out
