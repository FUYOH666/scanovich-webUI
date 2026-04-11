import base64
import json
import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

os.environ["LITELLM_BASE_URL"] = "http://litellm.test:4000"
os.environ["ORCHESTRATOR_API_KEY"] = "test-key"
os.environ["AUTO_ROUTE_MODEL"] = "true"
os.environ["ORCHESTRATOR_LITELLM_FALLBACK"] = "true"

from gpthub_orchestrator.main import app  # noqa: E402
from gpthub_orchestrator.model_registry import load_model_roles  # noqa: E402
from gpthub_orchestrator.settings import Settings  # noqa: E402


@pytest.fixture(autouse=True)
def clear_registry():
    load_model_roles.cache_clear()
    yield
    load_model_roles.cache_clear()


@pytest.mark.asyncio
async def test_non_stream_retries_on_429_then_200():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "litellm.test"
        body = json.loads(request.content.decode())
        calls.append(str(body.get("model")))
        if body.get("model") == "gpt-hub-turbo":
            return httpx.Response(429, json={"error": "rate_limited"})
        return httpx.Response(
            200,
            json={
                "id": "1",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model"),
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
            },
        )

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                auto_route_model=True,
                orchestrator_litellm_fallback=True,
                orchestrator_fallback_max_attempts=4,
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "model": "ignored-when-auto",
                    "messages": [
                        {"role": "user", "content": "What is a Python list in one sentence?"}
                    ],
                },
            )
        assert r.status_code == 200
        assert calls == ["gpt-hub-turbo", "gpt-hub-fallback"]
        trace_hdr = r.headers.get("X-GPTHub-Trace")
        assert trace_hdr
        raw = base64.b64decode(trace_hdr).decode("utf-8")
        trace = json.loads(raw)
        assert trace["orchestrator_fallback"]["retries_after_failure"] == 1
        assert trace["orchestrator_fallback"]["model_selected"] == "gpt-hub-fallback"
        assert trace["prompt_version"] == "v0.5.2"
        assert trace["classifier_source"] == "heuristic"
        assert trace["fallback_used"] is True
        assert trace.get("server_clock_iso")
    finally:
        await mock_inner.aclose()
