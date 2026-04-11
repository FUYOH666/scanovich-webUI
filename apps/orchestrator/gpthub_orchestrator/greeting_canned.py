"""Short-circuit trivial greetings without calling LiteLLM."""

from __future__ import annotations

import json
import time
from typing import Any


def greeting_canned_eligible(classification: dict[str, Any]) -> bool:
    if classification.get("task_type") != "greeting_or_tiny":
        return False
    modalities = classification.get("modalities") or []
    return "image" not in modalities


def client_visible_model_id(body: dict[str, Any], public_id: str) -> str:
    m = body.get("model")
    if isinstance(m, str) and m.strip():
        return m.strip()
    return public_id


def canned_chat_completion_json(
    *,
    model: str,
    content: str,
) -> dict[str, Any]:
    now = int(time.time())
    return {
        "id": "chatcmpl-gpthub-canned",
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def canned_chat_completion_sse_chunks(*, model: str, content: str) -> list[bytes]:
    """Minimal OpenAI-style stream: one delta with content, then finish, then [DONE]."""
    now = int(time.time())
    base = {
        "id": "chatcmpl-gpthub-canned",
        "object": "chat.completion.chunk",
        "created": now,
        "model": model,
    }
    delta_chunk = {
        **base,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    end_chunk = {
        **base,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    out = [
        f"data: {json.dumps(delta_chunk, ensure_ascii=False)}\n\n".encode("utf-8"),
        f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n".encode("utf-8"),
        b"data: [DONE]\n\n",
    ]
    return out
