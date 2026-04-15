"""Tests for ``pptx.plan`` — LiteLLM-backed slide planning (mocked HTTP)."""

from __future__ import annotations

import json

import httpx
import pytest

from gpthub_orchestrator.pptx import request_slide_plan
from gpthub_orchestrator.settings import Settings

_OUTLINE_SYS_MARKER = "deck outline (slide titles only)"
_ONE_SLIDE_SYS_MARKER = "exactly ONE slide"


@pytest.mark.asyncio
async def test_request_slide_plan_success(pptx_settings: Settings) -> None:
    outline = json.dumps(
        {"presentation_title": "Про тесты", "slides": [{"title": "S1", "kind": None}]}
    )
    slide1 = json.dumps(
        {"title": "S1", "bullets": ["x"], "notes": "", "kind": None},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/chat/completions")
        body = json.loads(request.content.decode())
        sys0 = body["messages"][0]["content"]
        if _OUTLINE_SYS_MARKER in sys0:
            assert "Tone: auto" in sys0
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": outline}}]},
            )
        assert _ONE_SLIDE_SYS_MARKER in sys0
        assert "Tone: auto" in sys0
        assert "timeline" in sys0
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": slide1}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        plan = await request_slide_plan(
            http,
            pptx_settings,
            [{"role": "user", "content": "Сделай презентацию про тесты"}],
        )
    assert plan.presentation_title == "Про тесты"
    assert plan.slides[0].title == "S1"


@pytest.mark.asyncio
async def test_request_slide_plan_json_retry_second_turn(pptx_settings: Settings) -> None:
    calls = {"n": 0}
    good = json.dumps(
        {
            "presentation_title": "QA deck",
            "slides": [{"title": "Fixed", "bullets": [], "notes": ""}],
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = json.loads(request.content.decode())
        sys0 = body["messages"][0]["content"]
        if calls["n"] == 1:
            assert _OUTLINE_SYS_MARKER in sys0
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "not json at all"}}]},
            )
        assert "Text density level" in sys0
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
    req = {"n": 0}
    outline = json.dumps(
        {"presentation_title": "Sprint review", "slides": [{"title": "R", "kind": None}]}
    )
    slide1 = json.dumps(
        {"title": "R", "bullets": [], "notes": "", "kind": None},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        m = str(body.get("model", ""))
        sys0 = body["messages"][0]["content"]
        models.append(m)
        req["n"] += 1
        if m == "gpt-hub-strong" and req["n"] == 1:
            return httpx.Response(429, json={"error": "rate"})
        if _OUTLINE_SYS_MARKER in sys0:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": outline}}]},
            )
        assert _ONE_SLIDE_SYS_MARKER in sys0
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": slide1}}]},
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
