"""Request structured slide plan from LiteLLM (strong / reasoning chain)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from gpthub_orchestrator.classifier import classify_messages
from gpthub_orchestrator.reasoning_response_filter import (
    merge_reasoning_exclude_into_body,
    strip_reasoning_from_completion_payload,
)
from gpthub_orchestrator.router import choose_model
from gpthub_orchestrator.settings import Settings

from gpthub_orchestrator.pptx.parse import parse_slide_plan_text
from gpthub_orchestrator.pptx.schema import PptxGenError, SlidePlan

logger = logging.getLogger(__name__)

_SYSTEM = """You output ONLY valid JSON for a slide deck plan. No markdown fences, no commentary before or after.
Schema exactly:
{"slides":[{"title":"string","bullets":["string"],"notes":"string"}]}
Rules:
- 1–20 slides.
- title: short heading.
- bullets: 0–8 strings per slide; each concise.
- notes: optional speaker notes (use "" if none).
- Escape any double quotes inside strings properly."""

_RETRY_USER = (
    "Your previous answer was not usable. Reply with ONLY one JSON object matching the schema "
    '{"slides":[{"title":"...","bullets":["..."],"notes":"..."}]} — no markdown, no prose.'
)


def _retryable_litellm_status(status_code: int) -> bool:
    return status_code in (429, 503)


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


def _conversation_excerpt(messages: list[dict[str, Any]], *, max_messages: int = 24) -> str:
    tail = messages[-max_messages:] if len(messages) > max_messages else messages
    blocks: list[str] = []
    for m in tail:
        role = str(m.get("role", "?"))
        text = _message_content_text(m.get("content")).strip()
        if len(text) > 8000:
            text = text[:8000] + "…"
        blocks.append(f"{role.upper()}:\n{text}")
    return "\n\n---\n\n".join(blocks)


def _auth_header(settings: Settings, authorization: str | None) -> str:
    if authorization and authorization.strip():
        return authorization.strip()
    return f"Bearer {settings.orchestrator_api_key}"


def _assistant_text(payload: dict[str, Any]) -> str:
    strip_reasoning_from_completion_payload(payload)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise PptxGenError("litellm_no_choices")
    ch0 = choices[0]
    if not isinstance(ch0, dict):
        raise PptxGenError("litellm_bad_choice")
    msg = ch0.get("message")
    if not isinstance(msg, dict):
        raise PptxGenError("litellm_no_message")
    content = msg.get("content")
    if not isinstance(content, str):
        raise PptxGenError("litellm_no_content")
    return content


async def _post_chat(
    http: httpx.AsyncClient,
    settings: Settings,
    *,
    model: str,
    messages: list[dict[str, str]],
    auth_header: str,
) -> dict[str, Any]:
    url = f"{settings.litellm_base_url.rstrip('/')}/v1/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.25,
        "max_tokens": 8192,
    }
    merge_reasoning_exclude_into_body(
        body,
        enabled=settings.orchestrator_request_reasoning_exclude,
    )
    r = await http.post(
        url,
        json=body,
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/json",
        },
    )
    if r.status_code >= 400:
        preview = r.text[:500]
        logger.warning("pptx_litellm_error status=%s preview=%s", r.status_code, preview)
        raise PptxGenError(f"litellm_http_{r.status_code}")
    try:
        data = r.json()
    except json.JSONDecodeError as e:
        raise PptxGenError("litellm_bad_json") from e
    if not isinstance(data, dict):
        raise PptxGenError("litellm_not_object")
    return data


async def _complete_plan_raw(
    http: httpx.AsyncClient,
    settings: Settings,
    *,
    chain: list[str],
    auth_header: str,
    messages: list[dict[str, str]],
) -> str:
    use_chain = settings.orchestrator_litellm_fallback and len(chain) > 0
    max_t = min(len(chain), settings.orchestrator_fallback_max_attempts) if use_chain else 1

    for i in range(max_t):
        alias = chain[i]
        try:
            data = await _post_chat(
                http,
                settings,
                model=alias,
                messages=messages,
                auth_header=auth_header,
            )
            return _assistant_text(data)
        except httpx.HTTPError as e:
            logger.warning("pptx_litellm_transport err=%s", e)
            raise PptxGenError("litellm_transport") from e
        except PptxGenError as e:
            if (
                use_chain
                and i < max_t - 1
                and str(e).startswith("litellm_http_")
            ):
                try:
                    code = int(str(e).removeprefix("litellm_http_"))
                except ValueError:
                    raise
                if _retryable_litellm_status(code):
                    continue
            raise

    raise PptxGenError("litellm_exhausted")


async def request_slide_plan(
    http: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, Any]],
    *,
    authorization: str | None = None,
) -> SlidePlan:
    """Call strong model (router pptx chain), parse JSON; one retry if JSON invalid."""
    classification = classify_messages(messages)
    if classification.get("task_type") != "pptx":
        logger.info("pptx_plan_task_mismatch got=%s", classification.get("task_type"))

    router = choose_model(classification, settings)
    chain = list(router.get("fallback_aliases") or [router["model_name"]])
    if not chain:
        raise PptxGenError("no_model_chain")

    base_user = (
        "Build a slide plan from this conversation. Honor the latest user request for topic/audience.\n\n"
        + _conversation_excerpt(messages)
    )
    auth = _auth_header(settings, authorization)

    initial_messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": base_user},
    ]

    raw = await _complete_plan_raw(
        http,
        settings,
        chain=chain,
        auth_header=auth,
        messages=initial_messages,
    )
    try:
        return parse_slide_plan_text(raw)
    except (ValueError, json.JSONDecodeError) as e:
        logger.info("pptx_plan_parse_retry err=%s", e)
        retry_msgs: list[dict[str, str]] = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": base_user},
            {"role": "assistant", "content": raw[:6000]},
            {"role": "user", "content": _RETRY_USER},
        ]
        raw2 = await _complete_plan_raw(
            http,
            settings,
            chain=chain,
            auth_header=auth,
            messages=retry_msgs,
        )
        try:
            return parse_slide_plan_text(raw2)
        except (ValueError, json.JSONDecodeError) as e2:
            logger.warning("pptx_plan_parse_failed err=%s", e2)
            raise PptxGenError("slide_plan_json_invalid") from e2
