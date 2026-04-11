"""Canned greeting short-circuit: no LiteLLM call, trace canned_response."""

from __future__ import annotations

import base64
import json
import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

os.environ["LITELLM_BASE_URL"] = "http://litellm.test:4000"
os.environ["ORCHESTRATOR_API_KEY"] = "test-key"

from gpthub_orchestrator.main import app  # noqa: E402
from gpthub_orchestrator.response_preamble_strip import assistant_content_has_leak_substrings  # noqa: E402
from gpthub_orchestrator.settings import Settings  # noqa: E402


@pytest.mark.asyncio
async def test_greeting_canned_skips_litellm_non_stream():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(500, json={"error": "upstream should not be called"})

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                greeting_canned_response_enabled=True,
                greeting_canned_message="Hi canned",
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={"model": "gpt-hub", "messages": [{"role": "user", "content": "привет"}]},
            )
        assert r.status_code == 200
        assert calls == []
        data = r.json()
        assert data["choices"][0]["message"]["content"] == "Hi canned"
        trace_hdr = r.headers.get("X-GPTHub-Trace")
        assert trace_hdr
        trace = json.loads(base64.b64decode(trace_hdr).decode("utf-8"))
        assert trace.get("canned_response") is True
        leaks = assistant_content_has_leak_substrings(data["choices"][0]["message"]["content"])
        assert leaks == []
    finally:
        await mock_inner.aclose()


@pytest.mark.asyncio
async def test_greeting_canned_disabled_calls_litellm():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        body = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "1",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model"),
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "from-upstream"}, "finish_reason": "stop"}
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
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={"model": "gpt-hub", "messages": [{"role": "user", "content": "привет"}]},
            )
        assert r.status_code == 200
        assert len(calls) == 1
        assert r.json()["choices"][0]["message"]["content"] == "from-upstream"
        trace_hdr = r.headers.get("X-GPTHub-Trace")
        assert trace_hdr
        trace = json.loads(base64.b64decode(trace_hdr).decode("utf-8"))
        assert trace.get("canned_response") is not True
    finally:
        await mock_inner.aclose()


@pytest.mark.asyncio
async def test_greeting_canned_stream_sse():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(500)

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                greeting_canned_response_enabled=True,
                greeting_canned_message="stream-hi",
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "model": "gpt-hub",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
            )
        assert r.status_code == 200
        assert calls == []
        raw = r.text
        assert "stream-hi" in raw
        assert "[DONE]" in raw
        trace_hdr = r.headers.get("X-GPTHub-Trace")
        assert trace_hdr
        trace = json.loads(base64.b64decode(trace_hdr).decode("utf-8"))
        assert trace.get("canned_response") is True
    finally:
        await mock_inner.aclose()


@pytest.mark.asyncio
async def test_greeting_plus_date_question_calls_litellm_not_canned():
    """Bundled greeting + factual question must not use canned (LLM answers with clock)."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        body = json.loads(request.content.decode())
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
                        "message": {"role": "assistant", "content": "from-upstream"},
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
                greeting_canned_response_enabled=True,
                greeting_canned_message="Hi canned",
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "model": "gpt-hub",
                    "messages": [{"role": "user", "content": "Привет, какой сегодня день?"}],
                },
            )
        assert r.status_code == 200
        assert len(calls) == 1
        assert r.json()["choices"][0]["message"]["content"] == "from-upstream"
        trace_hdr = r.headers.get("X-GPTHub-Trace")
        assert trace_hdr
        trace = json.loads(base64.b64decode(trace_hdr).decode("utf-8"))
        assert trace.get("canned_response") is not True
    finally:
        await mock_inner.aclose()


@pytest.mark.asyncio
async def test_casual_kak_dela_canned_skips_litellm():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(500)

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                greeting_canned_response_enabled=True,
                greeting_canned_message="Отлично, готов помочь!",
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={"model": "gpt-hub", "messages": [{"role": "user", "content": "как дела?"}]},
            )
        assert r.status_code == 200
        assert calls == []
        assert r.json()["choices"][0]["message"]["content"] == "Отлично, готов помочь!"
    finally:
        await mock_inner.aclose()

