"""Request structured slide plan from LiteLLM (strong / reasoning chain)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from pydantic import ValidationError

from gpthub_orchestrator.classifier import classify_messages
from gpthub_orchestrator.reasoning_response_filter import (
    merge_reasoning_exclude_into_body,
    strip_reasoning_from_completion_payload,
)
from gpthub_orchestrator.router import choose_model
from gpthub_orchestrator.settings import Settings

from gpthub_orchestrator.pptx.parse import (
    parse_outline_plan_text,
    parse_single_slide_detail_text,
    parse_slide_plan_text,
    slide_spec_from_agent_payload,
)
from gpthub_orchestrator.pptx.schema import ALLOWED_SLIDE_KINDS, PptxGenError, SlidePlan, SlideSpec

logger = logging.getLogger(__name__)

_DENSITY_RULES = """How to write bullets for the chosen text density (each array entry is one bullet):
- minimal: 1–2 short phrases per bullet, no fluff.
- concise: 2–3 short sentences (or tight phrases) per bullet.
- detailed: 3–4 sentences per bullet with light context.
- extensive: 4+ sentences per bullet only when the user clearly needs depth; prefer splitting into more slides if the deck grows too large."""


def _pptx_plan_system_prompt(settings: Settings) -> str:
    kinds = ", ".join(sorted(ALLOWED_SLIDE_KINDS))
    tc = settings.pptx_plan_text_content
    return f"""You output ONLY valid JSON for a slide deck plan. No markdown fences, no commentary before or after.
Schema exactly:
{{"slides":[{{"title":"string","bullets":["string"],"notes":"string","kind":"string or omit"}}]}}

Presentation context (adapt language; the user conversation defines topic and can override style):
- Tone: {settings.pptx_plan_tone}
- Target audience: {settings.pptx_plan_audience}
- Scenario: {settings.pptx_plan_scenario}
- Text density level for this run: {tc}

{_DENSITY_RULES}

Optional "kind" per slide — semantic layout intent; pick one string that fits the slide from:
{kinds}
Omit "kind" or use null if unsure. The deck builder may still use a simple template; "kind" guides structure and ordering of ideas.

Rules:
- 1–{settings.pptx_max_slides} slides.
- title: short heading.
- bullets: 0–8 strings per slide; follow the text density level above.
- notes: optional speaker notes (use "" if none).
- Escape any double quotes inside strings properly."""


def _pptx_outline_system_prompt(settings: Settings) -> str:
    kinds = ", ".join(sorted(ALLOWED_SLIDE_KINDS))
    return f"""You output ONLY valid JSON — deck outline (slide titles only). No markdown fences, no commentary.
Schema exactly:
{{"slides":[{{"title":"string","kind":"string or omit"}}]}}

Presentation context:
- Tone: {settings.pptx_plan_tone}
- Target audience: {settings.pptx_plan_audience}
- Scenario: {settings.pptx_plan_scenario}

Optional "kind" per slide — pick one that fits from:
{kinds}
Omit "kind" if unsure.

Rules:
- 1–{settings.pptx_max_slides} slides.
- Each item has only "title" and optionally "kind".
- Do not include "bullets" or "notes".
- Escape any double quotes inside strings properly."""


def _pptx_slide_agent_system_prompt(settings: Settings) -> str:
    kinds = ", ".join(sorted(ALLOWED_SLIDE_KINDS))
    tc = settings.pptx_plan_text_content
    return f"""You output ONLY valid JSON for exactly ONE slide. No markdown fences, no commentary.
Schema exactly:
{{"title":"string","bullets":["string"],"notes":"string","kind":"string or omit"}}

Presentation context (same deck as other slides):
- Tone: {settings.pptx_plan_tone}
- Target audience: {settings.pptx_plan_audience}
- Scenario: {settings.pptx_plan_scenario}
- Text density for bullets: {tc}

{_DENSITY_RULES}

Optional "kind" from:
{kinds}

Rules:
- The JSON "title" must match the assigned slide title exactly (same language and wording).
- bullets: 0–8 strings; follow the density level.
- notes: speaker notes or use "".
- Escape any double quotes inside strings properly."""


_RETRY_USER = (
    "Your previous answer was not usable. Reply with ONLY one JSON object matching the schema "
    '{"slides":[{"title":"...","bullets":["..."],"notes":"...","kind":null or one allowed kind}]} '
    "— no markdown, no prose."
)

_RETRY_SLIDE_USER = (
    "Your previous answer was not usable. Reply with ONLY one JSON object for this single slide: "
    '{"title":"...","bullets":["..."],"notes":"...","kind":null or allowed kind} — no markdown, no prose.'
)


def _log_pptx_timing(payload: dict[str, Any]) -> None:
    logger.info("pptx_timing %s", json.dumps(payload, ensure_ascii=False))


def _log_pptx_slide_agent_done(
    *,
    idx: int,
    total: int,
    spec: SlideSpec,
    ms: float | None,
    mode: str,
) -> None:
    payload: dict[str, Any] = {
        "phase": "pptx_slide_agent_done",
        "mode": mode,
        "idx": idx,
        "total": total,
        "title": spec.title,
        "kind": spec.kind,
        "bullets": spec.bullets,
        "notes": spec.notes,
    }
    if ms is not None:
        payload["ms"] = round(ms, 1)
    logger.info("pptx_timing %s", json.dumps(payload, ensure_ascii=False))


def _finalize_monolithic_plan(plan: SlidePlan) -> SlidePlan:
    for i, spec in enumerate(plan.slides):
        _log_pptx_slide_agent_done(
            idx=i,
            total=len(plan.slides),
            spec=spec,
            ms=None,
            mode="monolithic",
        )
    return plan


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
    max_tokens: int | None = None,
) -> dict[str, Any]:
    url = f"{settings.litellm_base_url.rstrip('/')}/v1/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.25,
        "max_tokens": 8192 if max_tokens is None else max_tokens,
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
    max_tokens: int | None = None,
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
                max_tokens=max_tokens,
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


def _router_chain_auth_excerpt(
    messages: list[dict[str, Any]],
    settings: Settings,
    *,
    authorization: str | None,
) -> tuple[list[str], str, str]:
    classification = classify_messages(messages)
    if classification.get("task_type") != "pptx":
        logger.info("pptx_plan_task_mismatch got=%s", classification.get("task_type"))

    router = choose_model(classification, settings)
    chain = list(router.get("fallback_aliases") or [router["model_name"]])
    if not chain:
        raise PptxGenError("no_model_chain")
    auth = _auth_header(settings, authorization)
    excerpt = _conversation_excerpt(messages)
    return chain, auth, excerpt


def _slide_agent_user_block(
    excerpt: str,
    *,
    slide_index: int,
    total_slides: int,
    title: str,
    kind: str | None,
    all_titles: list[str],
) -> str:
    numbered = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(all_titles))
    kh = kind if kind else "omit"
    return (
        f"Conversation:\n\n{excerpt}\n\n"
        f"Deck outline (titles in order):\n{numbered}\n\n"
        f"Write content for slide {slide_index + 1} of {total_slides} only.\n"
        f'Assigned title (JSON "title" must match this exactly): {title}\n'
        f"Outline kind hint: {kh}\n\n"
        "Return one JSON object for this slide only."
    )


async def _request_slide_plan_monolithic(
    http: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, Any]],
    *,
    authorization: str | None = None,
) -> SlidePlan:
    """Single LLM call: full plan JSON (legacy path)."""
    chain, auth, excerpt = _router_chain_auth_excerpt(messages, settings, authorization=authorization)
    system_prompt = _pptx_plan_system_prompt(settings)
    base_user = (
        "Build a slide plan from this conversation. Honor the latest user request for topic/audience.\n\n"
        + excerpt
    )
    initial_messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": base_user},
    ]
    t_llm = time.perf_counter()
    raw = await _complete_plan_raw(
        http,
        settings,
        chain=chain,
        auth_header=auth,
        messages=initial_messages,
    )
    _log_pptx_timing(
        {
            "phase": "plan_monolithic_llm_first_ms",
            "ms": round((time.perf_counter() - t_llm) * 1000, 1),
        }
    )
    try:
        return _finalize_monolithic_plan(parse_slide_plan_text(raw))
    except (ValueError, json.JSONDecodeError) as e:
        logger.info("pptx_plan_parse_retry err=%s", e)
        retry_msgs: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": base_user},
            {"role": "assistant", "content": raw[:6000]},
            {"role": "user", "content": _RETRY_USER},
        ]
        t_retry = time.perf_counter()
        raw2 = await _complete_plan_raw(
            http,
            settings,
            chain=chain,
            auth_header=auth,
            messages=retry_msgs,
        )
        _log_pptx_timing(
            {
                "phase": "plan_monolithic_llm_retry_ms",
                "ms": round((time.perf_counter() - t_retry) * 1000, 1),
            }
        )
        try:
            return _finalize_monolithic_plan(parse_slide_plan_text(raw2))
        except (ValueError, json.JSONDecodeError) as e2:
            logger.warning("pptx_plan_parse_failed err=%s", e2)
            raise PptxGenError("slide_plan_json_invalid") from e2


async def _request_slide_plan_parallel(
    http: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, Any]],
    *,
    authorization: str | None = None,
) -> SlidePlan:
    """Outline LLM call, then one LiteLLM call per slide (bounded concurrency)."""
    chain, auth, excerpt = _router_chain_auth_excerpt(messages, settings, authorization=authorization)
    outline_sys = _pptx_outline_system_prompt(settings)
    outline_user = (
        "Build only the slide title outline from this conversation. Honor the latest user request.\n\n"
        + excerpt
    )
    outline_messages: list[dict[str, str]] = [
        {"role": "system", "content": outline_sys},
        {"role": "user", "content": outline_user},
    ]
    t_outline = time.perf_counter()
    outline_raw = await _complete_plan_raw(
        http,
        settings,
        chain=chain,
        auth_header=auth,
        messages=outline_messages,
        max_tokens=2048,
    )
    outline_ms = (time.perf_counter() - t_outline) * 1000
    try:
        outline_plan = parse_outline_plan_text(outline_raw)
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("pptx_outline_parse_failed err=%s", e)
        raise PptxGenError("slide_plan_json_invalid") from e

    mx = settings.pptx_max_slides
    if len(outline_plan.slides) > mx:
        logger.info(
            "pptx_outline_truncated outline_slides=%s kept=%s",
            len(outline_plan.slides),
            mx,
        )
        outline_plan = SlidePlan(slides=list(outline_plan.slides[:mx]))

    n = len(outline_plan.slides)
    titles = [s.title for s in outline_plan.slides]
    _log_pptx_timing(
        {
            "phase": "plan_outline_llm_ms",
            "ms": round(outline_ms, 1),
            "slides": n,
            "outline": [{"title": s.title, "kind": s.kind} for s in outline_plan.slides],
        }
    )

    slide_sys = _pptx_slide_agent_system_prompt(settings)
    sem = asyncio.Semaphore(settings.pptx_slide_agents_concurrency)
    per_slide_ms: list[float] = []

    async def _one_slide(idx: int, skeleton: SlideSpec) -> SlideSpec:
        async with sem:
            t0 = time.perf_counter()
            user_block = _slide_agent_user_block(
                excerpt,
                slide_index=idx,
                total_slides=n,
                title=skeleton.title,
                kind=skeleton.kind,
                all_titles=titles,
            )
            agent_msgs: list[dict[str, str]] = [
                {"role": "system", "content": slide_sys},
                {"role": "user", "content": user_block},
            ]
            raw = await _complete_plan_raw(
                http,
                settings,
                chain=chain,
                auth_header=auth,
                messages=agent_msgs,
                max_tokens=3072,
            )
            try:
                payload = parse_single_slide_detail_text(raw)
                spec = slide_spec_from_agent_payload(
                    payload,
                    title_fallback=skeleton.title,
                    kind_fallback=skeleton.kind,
                )
            except (ValueError, json.JSONDecodeError, ValidationError) as e:
                logger.info("pptx_slide_agent_parse_retry idx=%s err=%s", idx, e)
                retry_msgs = agent_msgs + [
                    {"role": "assistant", "content": raw[:4000]},
                    {"role": "user", "content": _RETRY_SLIDE_USER},
                ]
                raw2 = await _complete_plan_raw(
                    http,
                    settings,
                    chain=chain,
                    auth_header=auth,
                    messages=retry_msgs,
                    max_tokens=3072,
                )
                try:
                    payload = parse_single_slide_detail_text(raw2)
                    spec = slide_spec_from_agent_payload(
                        payload,
                        title_fallback=skeleton.title,
                        kind_fallback=skeleton.kind,
                    )
                except (ValueError, json.JSONDecodeError, ValidationError) as e2:
                    raise PptxGenError(f"slide_agent_json_invalid idx={idx}") from e2
            elapsed = (time.perf_counter() - t0) * 1000
            per_slide_ms.append(elapsed)
            logger.debug("pptx_timing slide_agent idx=%s ms=%.1f", idx, elapsed)
            _log_pptx_slide_agent_done(
                idx=idx,
                total=n,
                spec=spec,
                ms=elapsed,
                mode="parallel_slide_agent",
            )
            return spec

    t_batch = time.perf_counter()
    filled = await asyncio.gather(*(_one_slide(i, s) for i, s in enumerate(outline_plan.slides)))
    wall_ms = (time.perf_counter() - t_batch) * 1000
    _log_pptx_timing(
        {
            "phase": "plan_slide_agents_ms",
            "wall_ms": round(wall_ms, 1),
            "slide_count": n,
            "concurrency": settings.pptx_slide_agents_concurrency,
            "slowest_slide_agent_ms": round(max(per_slide_ms), 1) if per_slide_ms else 0,
            "mean_slide_agent_ms": round(sum(per_slide_ms) / len(per_slide_ms), 1) if per_slide_ms else 0,
        }
    )
    return SlidePlan(slides=list(filled))


async def request_slide_plan(
    http: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, Any]],
    *,
    authorization: str | None = None,
) -> SlidePlan:
    """Strong model chain: parallel per-slide agents (default) or one monolithic JSON."""
    t0 = time.perf_counter()
    plan: SlidePlan
    if settings.pptx_parallel_slide_agents_enabled:
        try:
            plan = await _request_slide_plan_parallel(http, settings, messages, authorization=authorization)
        except Exception as e:
            logger.warning("pptx_parallel_plan_failed fallback_monolithic err=%s", e)
            plan = await _request_slide_plan_monolithic(http, settings, messages, authorization=authorization)
    else:
        plan = await _request_slide_plan_monolithic(http, settings, messages, authorization=authorization)

    mx = settings.pptx_max_slides
    if len(plan.slides) > mx:
        logger.info("pptx_plan_truncated plan_slides=%s kept=%s", len(plan.slides), mx)
        plan = SlidePlan(slides=list(plan.slides[:mx]))

    _log_pptx_timing(
        {
            "phase": "plan_total_ms",
            "ms": round((time.perf_counter() - t0) * 1000, 1),
            "slides": len(plan.slides),
            "parallel_slide_agents": settings.pptx_parallel_slide_agents_enabled,
        }
    )
    return plan
