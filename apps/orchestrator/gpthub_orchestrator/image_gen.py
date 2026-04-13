"""Image-generation short-circuit: detect intent and call MWS /images/generations."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

import httpx

from gpthub_orchestrator.classifier import RU_IMPERATIVE_CREATE_VERBS
from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)

# Shown as the first streaming delta while MWS image generation runs (Open WebUI shows it immediately).
IMAGE_STREAM_USER_STATUS = "Обрабатываю запрос\n\n"


def image_stream_chunk_ids() -> tuple[str, int]:
    return f"chatcmpl-img-{uuid.uuid4().hex[:12]}", int(time.time())


def _sse_data_line(obj: dict[str, Any]) -> bytes:
    return b"data: " + json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n\n"


def build_image_sse_status_chunk(model_label: str, cid: str, created: int) -> bytes:
    """First SSE event: user-visible wait text before ``generate_image_via_mws`` completes."""
    chunk: dict[str, Any] = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": IMAGE_STREAM_USER_STATUS},
                "finish_reason": None,
            }
        ],
    }
    return _sse_data_line(chunk)


def build_image_sse_content_chunks(
    model_label: str, prompt: str, image_ref: str, cid: str, created: int
) -> list[bytes]:
    """SSE events after status: image markdown body, finish, [DONE]."""
    content = f'![{prompt[:120]}]({image_ref})\n\n*Сгенерировано через MWS `{model_label}`.*'
    mid: dict[str, Any] = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content},
                "finish_reason": None,
            }
        ],
    }
    final: dict[str, Any] = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return [_sse_data_line(mid), _sse_data_line(final), b"data: [DONE]\n\n"]


def build_image_sse_error_chunks(model_label: str, cid: str, created: int) -> list[bytes]:
    """SSE completion after ``IMAGE_STREAM_USER_STATUS`` when MWS image gen fails (stream path)."""
    msg = "Не удалось сгенерировать изображение.\n"
    mid: dict[str, Any] = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "delta": {"content": msg},
                "finish_reason": None,
            }
        ],
    }
    final: dict[str, Any] = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return [_sse_data_line(mid), _sse_data_line(final), b"data: [DONE]\n\n"]


# Strong triggers: these regexes decide whether to short-circuit chat into image gen.
# Must match Russian + English imperative verbs with an image noun nearby.
_IMAGE_NOUNS_RU = r"(?:картинк\w*|изображен\w*|арт|постер|иллюстрац\w*|логотип\w*|обо\w*|иконк\w*|рисун\w*|фото\w*)"
_IMAGE_VERBS_RU = rf"(?:нарису\w*|сгенерир\w*|придумай|покажи|{RU_IMPERATIVE_CREATE_VERBS})"
_IMAGE_NOUNS_EN = r"(?:image|picture|photo|poster|illustration|logo|wallpaper|icon|artwork|drawing)"
_IMAGE_VERBS_EN = r"(?:draw|generate|create|make|design|render|produce)"

_IMAGE_INTENT_PATTERNS = [
    # Russian: verb + noun (or vice versa) within same sentence.
    re.compile(rf"\b{_IMAGE_VERBS_RU}\b[^.?!\n]{{0,60}}\b{_IMAGE_NOUNS_RU}\b", re.IGNORECASE | re.UNICODE),
    re.compile(rf"\b{_IMAGE_NOUNS_RU}\b[^.?!\n]{{0,60}}\b{_IMAGE_VERBS_RU}\b", re.IGNORECASE | re.UNICODE),
    re.compile(
        rf"\b{_IMAGE_NOUNS_RU}\b[^.?!\n]{{0,60}}\b(?:хочу|хотим|хотите|хочет)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    # Russian: "нарисуй <что угодно>" — standalone imperative (нарисовать/сгенерировать
    # без существительного в русском почти всегда означает картинку).
    re.compile(r"\b(?:нарису\w*|нарисовать|сгенерир\w*\s+картин\w*)\b", re.IGNORECASE | re.UNICODE),
    # English: verb + noun.
    re.compile(rf"\b{_IMAGE_VERBS_EN}\s+(?:an?\s+|me\s+an?\s+|a\s+|the\s+)?{_IMAGE_NOUNS_EN}\b", re.IGNORECASE),
    # English: noun + verb (same window as RU).
    re.compile(rf"\b{_IMAGE_NOUNS_EN}\b[^.?!\n]{{0,60}}\b{_IMAGE_VERBS_EN}\b", re.IGNORECASE),
    # English: strong standalone verbs that almost always mean image generation.
    re.compile(r"\b(?:draw|sketch|paint|illustrate|render)\b", re.IGNORECASE),
    # Slash command.
    re.compile(r"/image\s+\S", re.IGNORECASE),
    # Literal terminology.
    re.compile(r"\bimage(?:-|\s+)?gen(?:eration)?\b", re.IGNORECASE),
]


def is_image_generation_request(text: str) -> bool:
    if not text:
        return False
    s = text.strip()
    if not s:
        return False
    if len(s) > 2000:
        # Likely doc/analysis; don't hijack.
        return False
    for pat in _IMAGE_INTENT_PATTERNS:
        if pat.search(s):
            return True
    return False


def extract_image_prompt(text: str) -> str:
    """Strip leading imperative verbs to get a cleaner diffusion prompt.

    Falls back to the full text if we can't confidently trim.
    """
    s = text.strip()
    if s.lower().startswith("/image"):
        return s[len("/image") :].strip(" :-—")
    trimmed = re.sub(
        rf"^\s*(?:{_IMAGE_VERBS_RU}|{_IMAGE_VERBS_EN})\s+(?:мне\s+|me\s+an?\s+|a\s+|the\s+|an?\s+)?",
        "",
        s,
        count=1,
        flags=re.IGNORECASE | re.UNICODE,
    )
    trimmed = re.sub(
        rf"^\s*(?:{_IMAGE_NOUNS_RU}|{_IMAGE_NOUNS_EN})\s+(?:с\s+|with\s+|of\s+)?",
        "",
        trimmed,
        count=1,
        flags=re.IGNORECASE | re.UNICODE,
    )
    return trimmed.strip(" :—-.") or s


class ImageGenError(Exception):
    pass


async def generate_image_via_mws(
    http: httpx.AsyncClient,
    *,
    settings: Settings,
    prompt: str,
    size: str = "1024x1024",
) -> tuple[str, str]:
    """Call MWS /images/generations and return (image_url_or_data_uri, model_id).

    Raises ImageGenError on any failure.
    """
    base = settings.mws_gpt_api_base
    key = settings.mws_gpt_api_key
    if not base or not key:
        raise ImageGenError("mws_credentials_missing")
    url = base.rstrip("/") + "/images/generations"
    model = settings.image_gen_model
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    try:
        r = await http.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=httpx.Timeout(settings.image_gen_timeout_seconds, connect=15.0),
        )
    except httpx.HTTPError as e:
        logger.warning("image_gen_http_error err=%s", e)
        raise ImageGenError(f"http_error: {type(e).__name__}") from e
    if r.status_code >= 400:
        logger.warning("image_gen_status status=%s body=%s", r.status_code, r.text[:400])
        raise ImageGenError(f"status_{r.status_code}")
    try:
        data = r.json()
    except Exception as e:  # noqa: BLE001
        raise ImageGenError("invalid_json") from e
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ImageGenError("empty_data")
    first = items[0]
    if not isinstance(first, dict):
        raise ImageGenError("bad_item")
    url_str = first.get("url")
    if isinstance(url_str, str) and url_str:
        return url_str, model
    b64 = first.get("b64_json")
    if isinstance(b64, str) and b64:
        return f"data:image/png;base64,{b64}", model
    raise ImageGenError("no_url_or_b64")


def build_image_chat_completion(
    *,
    model_label: str,
    prompt: str,
    image_ref: str,
) -> dict[str, Any]:
    """Return OpenAI-compatible chat.completion object with inline markdown image."""
    content = f'![{prompt[:120]}]({image_ref})\n\n*Сгенерировано через MWS `{model_label}`.*'
    return {
        "id": f"chatcmpl-img-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def build_image_sse_chunks(model_label: str, prompt: str, image_ref: str) -> list[bytes]:
    """Full SSE sequence (status + image body + finish) for tests and non-async callers."""
    cid, created = image_stream_chunk_ids()
    return [
        build_image_sse_status_chunk(model_label, cid, created),
        *build_image_sse_content_chunks(model_label, prompt, image_ref, cid, created),
    ]
