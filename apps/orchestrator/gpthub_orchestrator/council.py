"""Expert Council (WOW-1): parallel multi-expert fan-out + synthesis.

Design: when the classifier detects a DEEP_RESEARCH task (slash-command
``/research``, or Russian/English "deep research" / "глубок(ое|ий) анализ"
cues), the orchestrator fans out the user's query to three MWS experts
via LiteLLM in parallel, then calls a synthesis pass that merges their
opinions into one answer that stays inside the "one chat flow" contract.

Experts (role-agnostic aliases from settings, default MWS mapping):

* ``gpt-hub-strong``        — generalist synthesizer (``glm-4.6-357b``).
* ``gpt-hub-reasoning-or``  — deep reasoning / coder (``qwen3-coder-480b``).
* ``gpt-hub-doc``           — long-context doc expert (``qwen2.5-72b``).

If at least ``council_min_branches_for_synthesis`` experts return, we
call ``council_synthesis_model`` with an explicit "you received N expert
opinions" prompt; otherwise we fall back to a single strong-only call.

All branch attempts, successes, failures, and timings land in the
``X-GPTHub-Trace`` ``council`` payload so the panel can see live what
just happened. The short-circuit returns one OpenAI-compatible
``chat.completion`` / SSE — it must never leak multiple assistant turns
to the client.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from gpthub_orchestrator.reasoning_response_filter import merge_reasoning_exclude_into_body
from gpthub_orchestrator.settings import Settings

# Strip <think>...</think> blocks that some MWS models (qwen3, glm) emit
# as raw CoT. We do NOT want to leak these into synthesis or the emergency
# composite — they waste context and look terrible in the UI.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def _strip_cot_blocks(text: str) -> str:
    """Remove ``<think>...</think>`` blocks (qwen3 / glm raw CoT).

    Contract: never return an empty string when the input is non-empty —
    some models emit the whole answer inside a single malformed ``<think>``
    envelope, and we'd rather show raw CoT than nothing at all. The caller
    is responsible for deciding whether to display.
    """
    if not text:
        return text
    original = text
    # Strip all well-formed <think>...</think> pairs.
    cleaned = _THINK_BLOCK_RE.sub("", text).strip()
    if cleaned:
        # If the result still contains an unclosed <think>, drop it ONLY
        # if there is meaningful text before it.
        lower = cleaned.lower()
        open_pos = lower.find("<think>")
        if open_pos > 0:
            head = cleaned[:open_pos].strip()
            if head:
                return head
        return cleaned
    # All content was inside <think> blocks. Fall back to stripping the
    # opening tag and any closing tag we find, but keep the meat — better
    # than returning empty string.
    fallback = re.sub(r"</?think>", "", original, flags=re.IGNORECASE).strip()
    return fallback or original.strip()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

# Slash command always wins.
_SLASH_RESEARCH = re.compile(r"(?:^|\s)/research\b", re.IGNORECASE)

# Natural language cues (RU + EN). Keep these tight so we don't hijack
# normal questions. "Глубокое исследование", "deep research", "проведи
# исследование", "expert council"...
_RESEARCH_PHRASES = [
    re.compile(r"\bdeep\s+research\b", re.IGNORECASE),
    re.compile(r"\bexpert\s+council\b", re.IGNORECASE),
    re.compile(r"\bмульти[- ]?эксперт\w*\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\bсовет\s+эксперт\w*\b", re.IGNORECASE | re.UNICODE),
    re.compile(
        r"\b(?:провед[иеё]|сделай|запусти)\b[^.?!\n]{0,40}\bглубок\w*\b[^.?!\n]{0,40}\b(?:исследован\w*|анализ\w*)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\bглубок\w*\s+(?:исследован\w*|анализ\w*)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\b(?:research|investigate|analyze)\b[^.?!\n]{0,60}\b(?:in\s+depth|deeply|thoroughly)\b",
        re.IGNORECASE,
    ),
]

# Open WebUI sends these as the last ``user`` message to the configured OpenAI base URL
# (same as user chat). They embed ``<chat_history>`` which may contain ``/research`` or
# research phrases and would false-trigger Expert Council if matched naïvely.
# v0.8.12: ``generate_queries`` (middleware) and follow-up suggestion task.
_RE_WEBUI_GENERATE_QUERIES_TASK = re.compile(
    r"### Task:\s*\r?\n\s*Analyze the chat history to determine the necessity of generating search queries",
    re.IGNORECASE,
)
_RE_WEBUI_FOLLOW_UP_SUGGESTIONS = re.compile(
    r"Suggest 3[\-–]5 relevant follow-up questions",
    re.IGNORECASE,
)
# task.title / task.tags / task.image.prompt / task.autocomplete (Open WebUI defaults, v0.8.x).
_RE_WEBUI_TITLE_GENERATION = re.compile(
    r"Generate a concise, 3[\-–]5 word title with an emoji summarizing the chat history",
    re.IGNORECASE,
)
_RE_WEBUI_TAGS_GENERATION = re.compile(
    r"Generate 1[\-–]3 broad tags categorizing the main themes of the chat history",
    re.IGNORECASE,
)
_RE_WEBUI_IMAGE_PROMPT_FOR_GEN = re.compile(
    r"Generate a detailed prompt for (?:an|am) image generation task",
    re.IGNORECASE,
)
_RE_WEBUI_AUTOCOMPLETE_TASK = re.compile(
    r"You are an autocompletion system\.\s*Continue the text",
    re.IGNORECASE | re.DOTALL,
)


def is_open_webui_internal_completion_user_text(text: str) -> bool:
    """True if ``text`` is a known Open WebUI synthetic user prompt (not real user intent)."""
    if not text or not text.strip():
        return False
    s = text.strip()
    if _RE_WEBUI_GENERATE_QUERIES_TASK.search(s):
        return True
    if _RE_WEBUI_FOLLOW_UP_SUGGESTIONS.search(s):
        return True
    if _RE_WEBUI_TITLE_GENERATION.search(s):
        return True
    if _RE_WEBUI_TAGS_GENERATION.search(s):
        return True
    if _RE_WEBUI_IMAGE_PROMPT_FOR_GEN.search(s):
        return True
    if _RE_WEBUI_AUTOCOMPLETE_TASK.search(s):
        return True
    return False


def is_council_request(text: str) -> bool:
    """True if the last user text should short-circuit into the Expert Council."""
    if not text:
        return False
    s = text.strip()
    if not s:
        return False
    # Hard ceiling: don't hijack a huge document paste into the council.
    if len(s) > 8000:
        return False
    if _SLASH_RESEARCH.search(s):
        return True
    for pat in _RESEARCH_PHRASES:
        if pat.search(s):
            return True
    return False


def extract_council_question(text: str) -> str:
    """Strip a leading ``/research`` marker. Return the original text otherwise."""
    s = text.strip()
    m = _SLASH_RESEARCH.search(s)
    if m and m.start() == 0:
        return s[m.end():].strip(" :—-")
    # Allow "/research <q>" mid-line too (just in case).
    if s.lower().startswith("/research"):
        return s[len("/research"):].strip(" :—-")
    return s


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ExpertSpec:
    """Config for a single branch in the council fan-out."""

    key: str  # "strong" | "reasoning" | "doc" (trace-friendly label)
    model: str  # LiteLLM alias
    persona: str  # persona prompt describing this expert's angle
    label: str  # human-readable label for the synthesized report


@dataclass
class ExpertOpinion:
    key: str
    model: str
    label: str
    content: str
    latency_ms: int


@dataclass
class ExpertFailure:
    key: str
    model: str
    error: str


@dataclass
class CouncilResult:
    final_text: str
    synthesis_model: str
    opinions: list[ExpertOpinion] = field(default_factory=list)
    failures: list[ExpertFailure] = field(default_factory=list)
    total_ms: int = 0
    fallback_used: bool = False  # True when we dropped to strong-only

    def trace_payload(self) -> dict[str, Any]:
        return {
            "short_circuit": "expert_council",
            "synthesis_model": self.synthesis_model,
            "branches_ok": [
                {
                    "key": o.key,
                    "model": o.model,
                    "label": o.label,
                    "latency_ms": o.latency_ms,
                    "chars": len(o.content),
                }
                for o in self.opinions
            ],
            "branches_failed": [
                {"key": f.key, "model": f.model, "error": f.error} for f in self.failures
            ],
            "total_ms": self.total_ms,
            "fallback_used": self.fallback_used,
        }


# ---------------------------------------------------------------------------
# Persona prompts
# ---------------------------------------------------------------------------

_PERSONA_STRONG = (
    "Ты — generalist-эксперт (strong). Твоя роль — дать ответ с верхнеуровневой"
    " картой темы: контекст, ключевые компоненты, плюсы/минусы, практические"
    " выводы. Пиши по-русски, 4–8 коротких абзацев, без воды, без markdown"
    " заголовков верхнего уровня. Если уверен — давай конкретные примеры."
)

_PERSONA_REASONING = (
    "Ты — reasoning-эксперт. Твоя роль — разобрать задачу как инженер: причинно-"
    "следственные связи, архитектурные trade-off'ы, крайние случаи, подводные"
    " камни. Пиши по-русски, структурируй через короткие нумерованные пункты,"
    " не больше 8 пунктов. Никаких цепочек рассуждений для клиента — только"
    " вывод."
)

_PERSONA_DOC = (
    "Ты — doc-эксперт по длинному контексту. Твоя роль — дать фактологический"
    " обзор: определения, ключевые термины, существующие подходы, что обычно"
    " пишут в авторитетных источниках. Пиши по-русски, 5–8 коротких абзацев,"
    " без сочинительства — если факт не подтверждён в предоставленном"
    " контексте, явно помечай его как «по распространённому представлению»."
)

_SYNTHESIS_INSTRUCTION_TEMPLATE = (
    "Ты — синтезатор Expert Council. Тебе дали исходный запрос пользователя и"
    " {n_opinions} экспертных мнений. Твоя задача — собрать ИТОГОВЫЙ ответ"
    " пользователю на русском языке так, чтобы:\n"
    "1. В начале коротко сформулировать суть (2–3 предложения);\n"
    "2. Далее под заголовком '**Что говорит совет экспертов:**' собрать"
    " ключевые пункты из мнений в связный анализ, НЕ пересказывая каждое"
    " мнение отдельно — объедини сходное, отметь расхождения, если есть;\n"
    "3. Закончить практическими рекомендациями 3–5 пунктами;\n"
    "4. Не ссылайся на «эксперт 1 / 2 / 3» и не раскрывай имена моделей;\n"
    "5. Не включай мета-рассуждения, только итоговый текст ответа;\n"
    "6. Markdown разрешён (списки, жирный шрифт, inline code), заголовки"
    " только h3 или меньше."
)


# ---------------------------------------------------------------------------
# LiteLLM calls
# ---------------------------------------------------------------------------


class CouncilError(Exception):
    pass


async def _call_litellm_chat(
    http: httpx.AsyncClient,
    *,
    base_url: str,
    auth_header: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    timeout_seconds: float,
) -> str:
    """Thin wrapper around LiteLLM ``/v1/chat/completions``.

    Returns the assistant text. Raises :class:`CouncilError` on any
    upstream failure — the caller decides whether to drop the branch
    or escalate.
    """
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    # Ask the upstream provider to suppress reasoning tokens so expensive
    # glm / qwen3 CoT doesn't eat the max_tokens budget before the real
    # answer gets emitted.
    merge_reasoning_exclude_into_body(payload, enabled=True)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    try:
        r = await http.post(
            url,
            headers=headers,
            json=payload,
            timeout=httpx.Timeout(timeout_seconds, connect=15.0),
        )
    except httpx.TimeoutException as e:
        raise CouncilError("timeout") from e
    except httpx.HTTPError as e:
        raise CouncilError(f"http_error: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise CouncilError(f"status_{r.status_code}: {r.text[:200]}")
    try:
        data = r.json()
    except Exception as e:  # noqa: BLE001
        raise CouncilError("invalid_json") from e
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise CouncilError("empty_choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise CouncilError("bad_choice")
    msg = first.get("message")
    if not isinstance(msg, dict):
        raise CouncilError("bad_message")
    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        raise CouncilError("empty_content")
    return content.strip()


def _build_expert_messages(spec: ExpertSpec, question: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": spec.persona},
        {"role": "user", "content": question},
    ]


def _build_synthesis_messages(question: str, opinions: list[ExpertOpinion]) -> list[dict[str, Any]]:
    lines: list[str] = [
        "Исходный запрос пользователя:",
        question.strip(),
        "",
        f"Мнения экспертов ({len(opinions)}):",
    ]
    for i, op in enumerate(opinions, start=1):
        lines.append("")
        lines.append(f"--- Мнение {i} ({op.label}) ---")
        lines.append(op.content)
    synthesis_user = "\n".join(lines)
    return [
        {
            "role": "system",
            "content": _SYNTHESIS_INSTRUCTION_TEMPLATE.format(n_opinions=len(opinions)),
        },
        {"role": "user", "content": synthesis_user},
    ]


def default_experts(settings: Settings) -> list[ExpertSpec]:
    return [
        ExpertSpec(
            key="strong",
            model=settings.council_expert_strong,
            persona=_PERSONA_STRONG,
            label="Generalist",
        ),
        ExpertSpec(
            key="reasoning",
            model=settings.council_expert_reasoning,
            persona=_PERSONA_REASONING,
            label="Reasoning",
        ),
        ExpertSpec(
            key="doc",
            model=settings.council_expert_doc,
            persona=_PERSONA_DOC,
            label="Doc/Long-context",
        ),
    ]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def _run_expert(
    http: httpx.AsyncClient,
    *,
    base_url: str,
    auth_header: str,
    spec: ExpertSpec,
    question: str,
    max_tokens: int,
    timeout_seconds: float,
) -> ExpertOpinion:
    t0 = time.monotonic()
    content = await _call_litellm_chat(
        http,
        base_url=base_url,
        auth_header=auth_header,
        model=spec.model,
        messages=_build_expert_messages(spec, question),
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    )
    # Drop raw chain-of-thought before handing this opinion to the
    # synthesis pass or the emergency composite.
    content = _strip_cot_blocks(content)
    return ExpertOpinion(
        key=spec.key,
        model=spec.model,
        label=spec.label,
        content=content,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


# (phase, experts_ready, experts_total); phase: experts | synthesis | synthesis_fallback.
CouncilProgressFn = Callable[[str, int, int], Awaitable[None]]


async def run_council(
    http: httpx.AsyncClient,
    *,
    settings: Settings,
    base_url: str,
    auth_header: str,
    question: str,
    experts: list[ExpertSpec] | None = None,
    progress: CouncilProgressFn | None = None,
) -> CouncilResult:
    """Run the Expert Council fan-out + synthesis.

    Returns :class:`CouncilResult`. Never raises: a fully-failed council
    produces a :class:`CouncilResult` with an explanatory ``final_text``
    and ``fallback_used=True`` so the short-circuit can still return one
    answer to the client.
    """
    if not question.strip():
        raise ValueError("question must be non-empty")
    experts = experts or default_experts(settings)
    total_start = time.monotonic()
    n_experts = len(experts)

    if progress is not None:
        await progress("experts", 0, n_experts)

    lock: asyncio.Lock | None = asyncio.Lock() if progress is not None else None
    expert_done = 0

    async def _expert_task(spec: ExpertSpec) -> ExpertOpinion | BaseException:
        nonlocal expert_done
        try:
            return await _run_expert(
                http,
                base_url=base_url,
                auth_header=auth_header,
                spec=spec,
                question=question,
                max_tokens=settings.council_max_expert_tokens,
                timeout_seconds=settings.council_branch_timeout_seconds,
            )
        except Exception as e:
            return e
        finally:
            if progress is not None and lock is not None:
                async with lock:
                    expert_done += 1
                    await progress("experts", expert_done, n_experts)

    tasks = [asyncio.create_task(_expert_task(spec), name=f"council_expert_{spec.key}") for spec in experts]
    raw = await asyncio.gather(*tasks)

    opinions: list[ExpertOpinion] = []
    failures: list[ExpertFailure] = []
    for spec, outcome in zip(experts, raw, strict=True):
        if isinstance(outcome, ExpertOpinion):
            opinions.append(outcome)
        else:
            err = (
                outcome
                if isinstance(outcome, BaseException)
                else RuntimeError("unexpected_non_exception")
            )
            failures.append(
                ExpertFailure(
                    key=spec.key,
                    model=spec.model,
                    error=f"{type(err).__name__}: {err}",
                )
            )
            logger.warning(
                "council_expert_failed key=%s model=%s err=%s",
                spec.key,
                spec.model,
                err,
            )

    # Strong-only fallback if too few branches succeeded.
    if len(opinions) < settings.council_min_branches_for_synthesis:
        logger.warning(
            "council_insufficient_branches ok=%d need=%d — falling back to strong-only",
            len(opinions),
            settings.council_min_branches_for_synthesis,
        )
        if progress is not None:
            await progress("synthesis_fallback", len(opinions), n_experts)
        try:
            fallback_text = await _call_litellm_chat(
                http,
                base_url=base_url,
                auth_header=auth_header,
                model=settings.council_synthesis_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — strong-эксперт. Дай подробный, структурированный"
                            " ответ по-русски. Это fallback-режим Expert Council."
                        ),
                    },
                    {"role": "user", "content": question},
                ],
                max_tokens=settings.council_max_synthesis_tokens,
                timeout_seconds=settings.council_synthesis_timeout_seconds,
            )
            fallback_text = _strip_cot_blocks(fallback_text)
        except CouncilError as e:
            fallback_text = (
                "Не удалось собрать Expert Council: все эксперты и fallback"
                f" завершились ошибкой. Последняя ошибка: {e}"
            )
        return CouncilResult(
            final_text=fallback_text,
            synthesis_model=settings.council_synthesis_model,
            opinions=opinions,
            failures=failures,
            total_ms=int((time.monotonic() - total_start) * 1000),
            fallback_used=True,
        )

    # Synthesis pass.
    synthesis_raw: str | None = None
    if progress is not None:
        await progress("synthesis", len(opinions), n_experts)
    try:
        synthesis_raw = await _call_litellm_chat(
            http,
            base_url=base_url,
            auth_header=auth_header,
            model=settings.council_synthesis_model,
            messages=_build_synthesis_messages(question, opinions),
            max_tokens=settings.council_max_synthesis_tokens,
            timeout_seconds=settings.council_synthesis_timeout_seconds,
        )
    except CouncilError as e:
        logger.warning("council_synthesis_failed err=%s", e)
    else:
        final_text = _strip_cot_blocks(synthesis_raw)
        # Heuristic: if the synthesizer exhausted its budget on CoT and
        # we're left with a fragment that looks like raw reasoning (e.g.
        # "1.  **Deconstruct the Request:**" — a Markdown meta-dump rather
        # than a real answer), treat synthesis as failed and fall through
        # to the emergency composite path below.
        looks_like_cot_dump = (
            "Deconstruct the" in final_text
            or final_text.lower().startswith("1.  **")
            or (final_text.count("**") > 20 and len(final_text) > 2000 and "совет экспертов" not in final_text.lower())
        )
        if not looks_like_cot_dump and final_text:
            return CouncilResult(
                final_text=final_text,
                synthesis_model=settings.council_synthesis_model,
                opinions=opinions,
                failures=failures,
                total_ms=int((time.monotonic() - total_start) * 1000),
                fallback_used=False,
            )
        logger.warning(
            "council_synthesis_cot_dump detected — dropping to emergency composite; chars=%d",
            len(final_text),
        )
    # Fall-through: either CouncilError above or detected CoT dump.
    # Emergency composite: concat opinions under human headers so the
    # user still sees all three voices rather than a 500.
    bits: list[str] = [
        "**Синтез не удался, показываю мнения экспертов «как есть»:**",
        "",
    ]
    for op in opinions:
        bits.append(f"### {op.label}")
        bits.append(op.content)
        bits.append("")
    final_text = "\n".join(bits).strip()
    return CouncilResult(
        final_text=final_text,
        synthesis_model=settings.council_synthesis_model,
        opinions=opinions,
        failures=failures,
        total_ms=int((time.monotonic() - total_start) * 1000),
        fallback_used=True,
    )


# ---------------------------------------------------------------------------
# OpenAI-compatible response builders
# ---------------------------------------------------------------------------


def build_council_chat_completion(*, model_label: str, text: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-council-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def build_council_sse_chunks(model_label: str, text: str) -> list[bytes]:
    cid = f"chatcmpl-council-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    first = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": text},
                "finish_reason": None,
            }
        ],
    }
    final = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return [
        b"data: " + _json.dumps(first, ensure_ascii=False).encode("utf-8") + b"\n\n",
        b"data: " + _json.dumps(final, ensure_ascii=False).encode("utf-8") + b"\n\n",
        b"data: [DONE]\n\n",
    ]
