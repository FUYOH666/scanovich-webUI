"""GET /help and chat short-circuit for user_help."""

from __future__ import annotations

import base64
import json
import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("LITELLM_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("ORCHESTRATOR_API_KEY", "test-key")

from gpthub_orchestrator.main import app  # noqa: E402
from gpthub_orchestrator.semantic_classifier import classify_messages_for_route  # noqa: E402
from gpthub_orchestrator.settings import Settings  # noqa: E402


@pytest.mark.asyncio
async def test_help_http_json():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/help")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "gpthub-orchestrator"
    assert "capabilities" in data
    assert any(c.get("id") == "pptx" for c in data["capabilities"])


@pytest.mark.asyncio
async def test_user_help_chat_skips_upstream():
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
                greeting_canned_response_enabled=False,
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={"model": "gpt-hub", "messages": [{"role": "user", "content": "/help"}]},
            )
        assert r.status_code == 200
        assert calls == []
        payload = r.json()
        assert "GET /help" in payload["choices"][0]["message"]["content"]
        trace_hdr = r.headers.get("X-GPTHub-Trace")
        assert trace_hdr
        trace = json.loads(base64.b64decode(trace_hdr).decode("utf-8"))
        assert trace.get("task_type") == "user_help"
        assert trace.get("canned_response") is True
    finally:
        await mock_inner.aclose()


@pytest.mark.asyncio
async def test_ambiguous_help_phrase_classifies_user_help():
    s = Settings(
        litellm_base_url="http://litellm.test:4000",
        orchestrator_api_key="test-key",
        classifier_semantic_enabled=False,
    )
    messages = [{"role": "user", "content": "мне нужен pdf, но ты умеешь только pptx?"}]
    async with httpx.AsyncClient() as http:
        out, src = await classify_messages_for_route(messages, s, http)
    assert src == "ambiguous_ru"
    assert out["task_type"] == "user_help"


@pytest.mark.asyncio
async def test_logo_in_deck_phrase_is_user_help_not_pptx_generation():
    s = Settings(
        litellm_base_url="http://litellm.test:4000",
        orchestrator_api_key="test-key",
        classifier_semantic_enabled=False,
    )
    messages = [{"role": "user", "content": "нарисуй логотип и вставь в презентацию"}]
    async with httpx.AsyncClient() as http:
        out, src = await classify_messages_for_route(messages, s, http)
    assert src == "ambiguous_ru"
    assert out["task_type"] == "user_help"


@pytest.mark.asyncio
async def test_ambiguous_pptx_exact_even_when_semantic_off():
    s = Settings(
        litellm_base_url="http://litellm.test:4000",
        orchestrator_api_key="test-key",
        classifier_semantic_enabled=False,
    )
    messages = [{"role": "user", "content": "бахни презу про наш стек"}]
    async with httpx.AsyncClient() as http:
        out, src = await classify_messages_for_route(messages, s, http)
    assert src == "ambiguous_ru"
    assert out["task_type"] == "pptx_generation"
