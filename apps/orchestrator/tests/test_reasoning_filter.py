"""Reasoning metadata stripped from completions and SSE lines."""

from __future__ import annotations

import json

import pytest

from gpthub_orchestrator.reasoning_response_filter import (
    REASONING_PAYLOAD_KEYS,
    filter_sse_data_line_json,
    merge_reasoning_exclude_into_body,
    strip_reasoning_from_completion_payload,
)


def test_strip_completion_message_and_choice():
    payload = {
        "choices": [
            {
                "index": 0,
                "reasoning_content": "secret",
                "message": {
                    "role": "assistant",
                    "content": "hi",
                    "reasoning": {"x": 1},
                    "thinking_blocks": [],
                },
                "finish_reason": "stop",
            }
        ],
        "reasoning": "root",
    }
    strip_reasoning_from_completion_payload(payload)
    msg = payload["choices"][0]["message"]
    assert "reasoning" not in msg
    assert "reasoning_content" not in msg
    assert "thinking_blocks" not in msg
    assert msg["content"] == "hi"
    assert "reasoning_content" not in payload["choices"][0]
    assert "reasoning" not in payload


def test_filter_sse_line_strips_delta():
    line = (
        'data: {"choices":[{"delta":{"content":"a","reasoning_content":"x"}}]}'
    )
    out = filter_sse_data_line_json(line, strip_enabled=True)
    obj = json.loads(out[6:])
    delta = obj["choices"][0]["delta"]
    assert "reasoning_content" not in delta
    assert delta["content"] == "a"


def test_filter_sse_done_unchanged():
    assert filter_sse_data_line_json("data: [DONE]", strip_enabled=True) == "data: [DONE]"


def test_merge_reasoning_exclude():
    body: dict = {}
    merge_reasoning_exclude_into_body(body, enabled=True)
    assert body["reasoning"] == {"exclude": True}
    body2: dict = {"reasoning": {"effort": "low"}}
    merge_reasoning_exclude_into_body(body2, enabled=True)
    assert body2["reasoning"]["exclude"] is True
    assert body2["reasoning"]["effort"] == "low"


def test_merge_reasoning_exclude_disabled():
    body = {"reasoning": {"exclude": False}}
    merge_reasoning_exclude_into_body(body, enabled=False)
    assert body["reasoning"]["exclude"] is False


def test_reasoning_keys_frozen_nonempty():
    assert "reasoning_content" in REASONING_PAYLOAD_KEYS


import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("LITELLM_BASE_URL", "http://litellm.test:4000")
os.environ.setdefault("ORCHESTRATOR_API_KEY", "test-key")

from gpthub_orchestrator.main import app  # noqa: E402
from gpthub_orchestrator.settings import Settings  # noqa: E402


@pytest.mark.asyncio
async def test_non_stream_orchestrator_strips_reasoning_and_sends_exclude():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen["reasoning"] = body.get("reasoning")
        return httpx.Response(
            200,
            json={
                "id": "1",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "visible only",
                            "reasoning_content": "should not reach client",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                greeting_canned_response_enabled=False,
                auto_route_model=False,
                orchestrator_request_reasoning_exclude=True,
                orchestrator_strip_reasoning_from_response=True,
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "model": "gpt-hub-strong",
                    "messages": [{"role": "user", "content": "Say one word: hello."}],
                },
            )
        assert r.status_code == 200
        msg = r.json()["choices"][0]["message"]
        assert msg["content"] == "visible only"
        assert "reasoning_content" not in msg
        assert seen.get("reasoning", {}).get("exclude") is True
    finally:
        await mock_inner.aclose()
