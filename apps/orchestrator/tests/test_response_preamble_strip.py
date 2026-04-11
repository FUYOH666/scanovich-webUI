"""Known CoT preamble strip (non-stream path) and leak regression helpers."""

from __future__ import annotations

import json
import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from gpthub_orchestrator.response_preamble_strip import (
    BAD_LEAK_SUBSTRINGS,
    assistant_content_has_leak_substrings,
    strip_known_cot_preamble,
)

os.environ.setdefault("LITELLM_BASE_URL", "http://litellm.test:4000")
os.environ.setdefault("ORCHESTRATOR_API_KEY", "test-key")

from gpthub_orchestrator.main import app  # noqa: E402
from gpthub_orchestrator.settings import Settings  # noqa: E402


def test_strip_thinking_head_paragraph():
    raw = (
        "Here's a thinking process:\n\n"
        "Analyze user input: greeting.\n"
        "Check constraints: none.\n\n"
        "Hello, how can I help?"
    )
    out, applied = strip_known_cot_preamble(raw)
    assert applied
    assert "Hello, how can I help?" in out
    assert "analyze user input" not in out.lower()


def test_strip_leading_meta_lines():
    raw = "Analyze user input: x\nCheck constraints: y\n\nReal answer here."
    out, applied = strip_known_cot_preamble(raw)
    assert applied
    assert out.startswith("Real answer")


def test_bad_leak_substrings_constant_nonempty():
    assert len(BAD_LEAK_SUBSTRINGS) >= 5


def test_assistant_content_has_leak_substrings_detects():
    text = "Here is a thinking process: blah"
    hits = assistant_content_has_leak_substrings(text)
    assert "thinking process" in hits or "here is a thinking process" in hits


@pytest.mark.asyncio
async def test_non_stream_strip_flag_strips_completion():
    def handler(request: httpx.Request) -> httpx.Response:
        messy = (
            "Analyze user input: test\n"
            "Final output:\n\n"
            "Clean visible reply only."
        )
        return httpx.Response(
            200,
            json={
                "id": "1",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": messy}, "finish_reason": "stop"}
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
                orchestrator_strip_known_cot_preamble=True,
                auto_route_model=False,
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "model": "gpt-hub-strong",
                    "messages": [{"role": "user", "content": "Say hello in one line."}],
                },
            )
        assert r.status_code == 200
        content = r.json()["choices"][0]["message"]["content"]
        assert "Clean visible reply only." in content
        assert assistant_content_has_leak_substrings(content) == []
    finally:
        await mock_inner.aclose()
