import json
import os

import httpx
import pytest

os.environ.setdefault("LITELLM_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("ORCHESTRATOR_API_KEY", "k")

from gpthub_orchestrator.model_registry import load_model_roles
from gpthub_orchestrator.pptx import (
    PptxGenError,
    SlidePlan,
    SlideSpec,
    build_pptx_from_plan,
    extract_json_object,
    parse_slide_plan_text,
    request_slide_plan,
)
from gpthub_orchestrator.settings import Settings


@pytest.fixture(autouse=True)
def clear_registry_cache():
    load_model_roles.cache_clear()
    yield
    load_model_roles.cache_clear()


def _settings(**kwargs):
    base = {
        "litellm_base_url": "http://litellm.test",
        "orchestrator_api_key": "k",
    }
    base.update(kwargs)
    return Settings(**base)


def test_extract_json_object_fence():
    raw = 'Sure\n```json\n{"slides":[]}\n```\n'
    assert '"slides"' in extract_json_object(raw)


def test_parse_slide_plan_text_minimal():
    text = json.dumps(
        {
            "slides": [
                {"title": "Intro", "bullets": ["a", "b"], "notes": "say hi"},
            ]
        }
    )
    plan = parse_slide_plan_text(text)
    assert len(plan.slides) == 1
    assert plan.slides[0].title == "Intro"
    assert plan.slides[0].bullets == ["a", "b"]


def test_build_pptx_from_plan_zip_magic():
    plan = SlidePlan(
        slides=[
            SlideSpec(title="T", bullets=["one"], notes=""),
        ],
    )
    blob = build_pptx_from_plan(plan)
    assert blob.startswith(b"PK")


def test_build_pptx_empty_plan_raises():
    with pytest.raises(PptxGenError, match="empty_plan"):
        build_pptx_from_plan(SlidePlan(slides=[]))


@pytest.mark.asyncio
async def test_request_slide_plan_success():
    good = json.dumps(
        {"slides": [{"title": "S1", "bullets": ["x"], "notes": ""}]}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/chat/completions")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": good}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        plan = await request_slide_plan(
            http,
            _settings(),
            [{"role": "user", "content": "Сделай презентацию про тесты"}],
        )
    assert plan.slides[0].title == "S1"


@pytest.mark.asyncio
async def test_request_slide_plan_json_retry_second_turn():
    calls = {"n": 0}
    good = json.dumps(
        {"slides": [{"title": "Fixed", "bullets": [], "notes": ""}]}
    )

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
            _settings(),
            [{"role": "user", "content": "/pptx about QA"}],
        )
    assert calls["n"] == 2
    assert plan.slides[0].title == "Fixed"


@pytest.mark.asyncio
async def test_request_slide_plan_chain_429_then_ok():
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
            _settings(),
            [{"role": "user", "content": "build deck for sprint review"}],
        )
    assert models[0] == "gpt-hub-strong"
    assert models[1] == "gpt-hub-turbo"
    assert plan.slides[0].title == "R"
