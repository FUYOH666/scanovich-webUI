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

_USER_HELP_NL = re.compile(
    r"(?:^|\b)(?:что\s+ты\s+умеешь|что\s+умеешь|что\s+ты\s+можешь|что\s+можешь|"
    r"что\s+умеет(?:\s+эта)?\s+(?:программа|система|модель|ты)\b|"
    r"список\s+возможност|ваши?\s+возможност|как(?:ие)?\s+команды|"
    r"покажи\s+помощь|нужна\s+помощь\s+по\s+(?:боту|сервису|оркестратору))\b",
    re.IGNORECASE | re.UNICODE,
)


def _is_user_help_request(text: str) -> bool:
    """Свободная форма запроса возможностей / помощи (кроме таблицы ambiguous в semantic_classifier)."""
    s = text.strip()
    if not s:
        return False
    if re.match(r"^\s*/help\b", s, re.IGNORECASE):
        return True
    return bool(_USER_HELP_NL.search(s))


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
    USER_HELP = "user_help"
    IMAGE_GENERATION = "image_generation"
    SIMPLE_CHAT = "simple_chat"
    GREETING_OR_TINY = "greeting_or_tiny"
    CODE_HELP = "code_help"
    FILE_ANALYSIS = "file_analysis"
    SUMMARIZATION = "summarization"
    IMAGE_ANALYSIS = "image_analysis"
    AUDIO_ANALYSIS = "audio_analysis"
    MULTIMODAL_WORKFLOW = "multimodal_workflow"
    PPTX = "pptx"
    DEEP_RESEARCH = "deep_research"
    PPTX_GENERATION = "pptx_generation"


# PPTX: strong phrases beat doc/code heuristics; weak cues stay below doc-heavy / code / analyze.
_PPTX_STRONG = re.compile(
    r"(?:^|[\s,./])/pptx\b|"
    r"(?:сделай|сделайте|создай|создайте|подготовь|подготовьте|напиши|напишите|"
    r"сгенерируй|сгенерируйте|составь|составьте)\s+презентац|"
    r"презентаци[яию]\s+по\s+(?:этому|этой|этим|документу|тексту|файлу|материалу|теме)\b|"
    r"build\s+(?:a\s+)?deck\b|"
    r"make\s+(?:a\s+)?presentation\b|"
    r"generate\s+(?:a\s+)?presentation\b",
    re.IGNORECASE | re.UNICODE,
)
_PPTX_WEAK_SLIDES_RU = re.compile(
    r"(?:сделай|сделайте|создай|создайте|нужны|подготовь|подготовьте|сгенерируй|сгенерируйте)\s+слайд",
    re.IGNORECASE | re.UNICODE,
)
_PPTX_WEAK_EN = re.compile(
    r"\b(?:outline|draft)\s+(?:a\s+)?deck\b|"
    r"\bslides?\s+(?:for|about|on)\s+\w",
    re.IGNORECASE | re.UNICODE,
)
_PPTX_WEAK_DECK_PAIR = re.compile(
    r"\bdeck\b.*\b(?:slides?|презентац|pptx|powerpoint)\b|"
    r"\b(?:slides?|презентац|pptx|powerpoint)\b.*\bdeck\b",
    re.IGNORECASE | re.UNICODE,
)


def _pptx_intent_strong(text: str) -> bool:
    return bool(_PPTX_STRONG.search(text))


def _pptx_intent_weak(text: str, lower: str) -> bool:
    if _PPTX_WEAK_SLIDES_RU.search(lower):
        return True
    if _PPTX_WEAK_EN.search(lower):
        return True
    if len(text.strip()) < 32:
        return False
    return bool(_PPTX_WEAK_DECK_PAIR.search(lower))


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

    pptx_strong = _pptx_intent_strong(last_user)
    heavier_doc_or_code = doc_hints or code_hints or analyze_hints
    pptx_weak_ok = _pptx_intent_weak(last_user, lower) and not heavier_doc_or_code
    wants_pptx = pptx_strong or pptx_weak_ok

    # Expert Council (deep research) wins over PPTX for text-only prompts; `is_council_request`
    # is only evaluated without an image. Images: non-PPTX → image analysis; PPTX phrasing → pptx.
    # We lazy-import here to avoid a classifier↔council import cycle.
    deep_research_hit = False
    pptx_hit = False
    if not has_image:
        from gpthub_orchestrator.council import is_council_request  # local import to avoid cycle
        from gpthub_orchestrator.pptx_gen import is_pptx_request  # local import to avoid cycle

        deep_research_hit = is_council_request(last_user)
        pptx_hit = is_pptx_request(last_user)

    if _is_user_help_request(last_user):
        task = TaskType.USER_HELP
    elif has_image and (analyze_hints or code_hints):
        task = TaskType.MULTIMODAL_WORKFLOW
    elif has_image and not wants_pptx:
        task = TaskType.IMAGE_ANALYSIS
    elif pptx_hit:
        task = TaskType.PPTX_GENERATION
    elif deep_research_hit:
        task = TaskType.DEEP_RESEARCH
    elif wants_pptx:
        task = TaskType.PPTX
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
    if task == TaskType.PPTX:
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
