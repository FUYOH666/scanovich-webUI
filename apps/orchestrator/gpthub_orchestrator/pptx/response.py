"""OpenAI-style chat completion payloads for PPTX short-circuit."""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

from gpthub_orchestrator.pptx.schema import SlidePlan

_MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# Open WebUI (and some proxies) reject a single SSE JSON line over ~1MB; Slidesgo decks
# inflate to multi‑MB base64. Split `delta.content` across many chunks (concatenated by clients).
_SSE_CONTENT_SLICE_CHARS = 12_288


def markdown_preview_with_download(plan: SlidePlan, pptx_bytes: bytes) -> str:
    lines = ["### Превью слайдов", ""]
    for i, spec in enumerate(plan.slides, start=1):
        title = (spec.title or "").strip() or "(без заголовка)"
        kind = (spec.kind or "").strip()
        if kind:
            lines.append(f"{i}. **{title}** · _макет: `{kind}`_")
        else:
            lines.append(f"{i}. **{title}**")
    lines.append("")
    b64 = base64.standard_b64encode(pptx_bytes).decode("ascii")
    uri = f"data:{_MIME_PPTX};base64,{b64}"
    lines.append(f"[Скачать презентацию]({uri})")
    return "\n".join(lines)


def build_pptx_chat_completion(
    *,
    model_label: str,
    plan: SlidePlan,
    pptx_bytes: bytes,
) -> dict[str, Any]:
    content = markdown_preview_with_download(plan, pptx_bytes)
    return {
        "id": f"chatcmpl-pptx-{uuid.uuid4().hex[:12]}",
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


def build_pptx_error_chat_completion(*, model_label: str, message: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-pptx-err-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": message},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _slice_assistant_content_for_sse(text: str, *, max_chars: int = _SSE_CONTENT_SLICE_CHARS) -> list[str]:
    if not text:
        return [""]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def build_pptx_sse_chunks(*, model_label: str, plan: SlidePlan, pptx_bytes: bytes) -> list[bytes]:
    content = markdown_preview_with_download(plan, pptx_bytes)
    pieces = _slice_assistant_content_for_sse(content)
    cid = f"chatcmpl-pptx-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    out: list[bytes] = []
    for i, piece in enumerate(pieces):
        if i == 0:
            delta: dict[str, Any] = {"role": "assistant", "content": piece}
        else:
            delta = {"content": piece}
        chunk = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_label,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        out.append(b"data: " + json.dumps(chunk, ensure_ascii=False).encode("utf-8") + b"\n\n")
    final = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    out.append(b"data: " + json.dumps(final, ensure_ascii=False).encode("utf-8") + b"\n\n")
    out.append(b"data: [DONE]\n\n")
    return out


def build_pptx_error_sse_chunks(*, model_label: str, message: str) -> list[bytes]:
    cid = f"chatcmpl-pptx-err-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    first = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": message}, "finish_reason": None}],
    }
    final = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return [
        b"data: " + json.dumps(first, ensure_ascii=False).encode("utf-8") + b"\n\n",
        b"data: " + json.dumps(final, ensure_ascii=False).encode("utf-8") + b"\n\n",
        b"data: [DONE]\n\n",
    ]
