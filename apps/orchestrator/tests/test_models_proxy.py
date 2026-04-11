import json
import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("LITELLM_BASE_URL", "http://litellm.test:4000")
os.environ.setdefault("ORCHESTRATOR_API_KEY", "test-key")

from gpthub_orchestrator.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_v1_models_catalog_all_passthrough():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/v1/models"):
            return httpx.Response(
                200,
                json={"object": "list", "data": [{"id": "gpt-hub-strong", "object": "model"}]},
            )
        return httpx.Response(404)

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = __import__(
                "gpthub_orchestrator.settings",
                fromlist=["Settings"],
            ).Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                orchestrator_models_catalog="all",
            )
            app.state.http = mock_inner
            r = await ac.get("/v1/models", headers={"Authorization": "Bearer test-key"})
        assert r.status_code == 200
        body = r.json()
        assert body["data"][0]["id"] == "gpt-hub-strong"
    finally:
        await mock_inner.aclose()


@pytest.mark.asyncio
async def test_v1_models_single_public_facade():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/v1/models"):
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": "gpt-hub-fast", "object": "model", "owned_by": "litellm"},
                        {"id": "gpt-hub-strong", "object": "model"},
                    ],
                },
            )
        return httpx.Response(404)

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            app.state.settings = __import__(
                "gpthub_orchestrator.settings",
                fromlist=["Settings"],
            ).Settings(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                orchestrator_models_catalog="single_public",
                orchestrator_public_model_id="gpt-hub",
            )
            app.state.http = mock_inner
            r = await ac.get("/v1/models", headers={"Authorization": "Bearer test-key"})
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == "gpt-hub"
        assert body["data"][0]["object"] == "model"
        assert body["data"][0].get("owned_by") == "litellm"
    finally:
        await mock_inner.aclose()


@pytest.mark.asyncio
async def test_chat_facade_id_maps_when_auto_route_off():
    seen_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/v1/chat/completions"):
            body = json.loads(request.content.decode())
            seen_models.append(str(body.get("model")))
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
        return httpx.Response(404)

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            S = __import__("gpthub_orchestrator.settings", fromlist=["Settings"]).Settings
            app.state.settings = S(
                litellm_base_url="http://litellm.test:4000",
                orchestrator_api_key="test-key",
                auto_route_model=False,
                orchestrator_litellm_fallback=False,
                default_text_model="gpt-hub-turbo",
                orchestrator_public_model_id="gpt-hub",
            )
            app.state.http = mock_inner
            r = await ac.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "model": "gpt-hub",
                    "messages": [{"role": "user", "content": "What is 2+2 in one sentence?"}],
                },
            )
        assert r.status_code == 200
        assert seen_models == ["gpt-hub-turbo"]
    finally:
        await mock_inner.aclose()
