import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

os.environ["LITELLM_BASE_URL"] = "http://litellm.test:4000"
os.environ["ORCHESTRATOR_API_KEY"] = "test-key"

from gpthub_orchestrator.main import app  # noqa: E402
from gpthub_orchestrator.settings import Settings  # noqa: E402


@pytest.mark.asyncio
async def test_readyz_ok_when_litellm_alive():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health/liveliness"):
            return httpx.Response(200, json={"status": "alive"})
        return httpx.Response(404)

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        app.state.settings = Settings(
            litellm_base_url="http://litellm.test:4000",
            orchestrator_api_key="test-key",
        )
        app.state.http = mock_inner
        r = await ac.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_readyz_503_when_litellm_down():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    mock_inner = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        app.state.settings = Settings(
            litellm_base_url="http://litellm.test:4000",
            orchestrator_api_key="test-key",
        )
        app.state.http = mock_inner
        r = await ac.get("/readyz")
    assert r.status_code == 503
