"""PPTX short-circuit: LiteLLM plan mock + trace pptx field."""

from __future__ import annotations

import base64
import json
import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("LITELLM_BASE_URL", "http://litellm.test:4000")
os.environ.setdefault("ORCHESTRATOR_API_KEY", "test-key")

from gpthub_orchestrator.main import app  # noqa: E402
from gpthub_orchestrator.settings import Settings  # noqa: E402


@pytest.mark.asyncio
async def test_pptx_short_circuit_non_stream_ok():
    plan_json = json.dumps(
        {
            "slides": [
                {"title": "Введение", "bullets": ["пункт а"], "notes": ""},
                {"title": "Итог", "bullets": [], "notes": "спасибо"},
            ]
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/chat/completions")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": plan_json}}]},
        )

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=120.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                pptx_gen_enabled=True,
                image_gen_enabled=False,
                greeting_canned_response_enabled=False,
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "model": "gpt-hub",
                    "messages": [{"role": "user", "content": "Сделай презентацию про демо"}],
                },
            )
    finally:
        await mock_inner.aclose()

    assert r.status_code == 200
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    assert "Превью слайдов" in content
    assert "Введение" in content
    assert "Скачать презентацию" in content
    assert "data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64," in content

    trace_hdr = r.headers.get("X-GPTHub-Trace")
    assert trace_hdr
    trace = json.loads(base64.b64decode(trace_hdr).decode("utf-8"))
    assert trace.get("pptx") == {"status": "ok", "slides": 2}
    assert "orchestrator_fallback" not in trace


@pytest.mark.asyncio
async def test_pptx_short_circuit_plan_invalid_returns_200_with_trace_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json"}}]},
        )

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=120.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                pptx_gen_enabled=True,
                image_gen_enabled=False,
                greeting_canned_response_enabled=False,
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "model": "gpt-hub",
                    "messages": [{"role": "user", "content": "/pptx smoke"}],
                },
            )
    finally:
        await mock_inner.aclose()

    assert r.status_code == 200
    data = r.json()
    assert "Не удалось собрать" in data["choices"][0]["message"]["content"]
    trace = json.loads(base64.b64decode(r.headers["X-GPTHub-Trace"]).decode("utf-8"))
    assert trace["pptx"]["status"] == "error"
    assert trace["pptx"]["reason"] == "slide_plan_json_invalid"
