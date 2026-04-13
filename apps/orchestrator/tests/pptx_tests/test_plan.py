"""Tests for ``pptx.plan`` — LiteLLM-backed slide planning (mocked HTTP)."""

from __future__ import annotations

import json

import httpx
import pytest

from gpthub_orchestrator.pptx import request_slide_plan
from gpthub_orchestrator.settings import Settings


@pytest.mark.asyncio
async def test_request_slide_plan_success(pptx_settings: Settings) -> None:
    good = json.dumps({"slides": [{"title": "S1", "bullets": ["x"], "notes": ""}]})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/chat/completions")
        body = json.loads(request.content.decode())
        sys0 = body["messages"][0]["content"]
        assert "Tone: auto" in sys0
        assert "Text density level" in sys0
        assert "timeline" in sys0
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": good}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        plan = await request_slide_plan(
            http,
            pptx_settings,
            [{"role": "user", "content": "Сделай презентацию про тесты"}],
        )
    assert plan.slides[0].title == "S1"


@pytest.mark.asyncio
async def test_request_slide_plan_json_retry_second_turn(pptx_settings: Settings) -> None:
    calls = {"n": 0}
    good = json.dumps({"slides": [{"title": "Fixed", "bullets": [], "notes": ""}]})

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "not json at all"}}]},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": good}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        plan = await request_slide_plan(
            http,
            pptx_settings,
            [{"role": "user", "content": "/pptx about QA"}],
        )
    assert calls["n"] == 2
    assert plan.slides[0].title == "Fixed"


@pytest.mark.asyncio
async def test_request_slide_plan_chain_429_then_ok(pptx_settings: Settings) -> None:
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        models.append(str(body.get("model", "")))
        if body.get("model") == "gpt-hub-strong":
            return httpx.Response(429, json={"error": "rate"})
        good = json.dumps({"slides": [{"title": "R", "bullets": [], "notes": ""}]})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": good}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        plan = await request_slide_plan(
            http,
            pptx_settings,
            [{"role": "user", "content": "build deck for sprint review"}],
        )
    assert models[0] == "gpt-hub-strong"
    assert models[1] == "gpt-hub-turbo"
    assert plan.slides[0].title == "R"
