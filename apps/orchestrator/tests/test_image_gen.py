"""Image generation: intent detection, MWS call, chat-completion shape."""

from __future__ import annotations

import httpx
import pytest

from gpthub_orchestrator.image_gen import (
    ImageGenError,
    build_image_chat_completion,
    extract_image_prompt,
    generate_image_via_mws,
    is_image_generation_request,
)
from gpthub_orchestrator.settings import Settings


def _mk_settings(**over) -> Settings:
    base = {
        "litellm_base_url": "http://litellm:4000",
        "orchestrator_api_key": "t",
        "mws_gpt_api_base": "https://api.gpt.mws.ru/v1",
        "mws_gpt_api_key": "sk-test",
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Нарисуй картинку кота в шляпе",
        "Сгенерируй изображение красного яблока",
        "Создай логотип для стартапа",
        "draw a small red apple",
        "generate an image of mars",
        "make me a poster with mountains",
        "/image a cat on a rocket",
    ],
)
def test_image_intent_positive(text: str):
    assert is_image_generation_request(text)


@pytest.mark.parametrize(
    "text",
    [
        "Объясни, как работает нейросеть",
        "What's the weather today?",
        "Напиши функцию на python",
        "Suggest architecture for a chat app",
        "",
        "Привет!",
    ],
)
def test_image_intent_negative(text: str):
    assert not is_image_generation_request(text)


def test_extract_prompt_strips_imperative_verb():
    out = extract_image_prompt("Нарисуй большое красное яблоко на белом фоне")
    assert "яблоко" in out
    assert "Нарисуй" not in out


def test_extract_prompt_slashcommand():
    out = extract_image_prompt("/image a futuristic city at sunset")
    assert out == "a futuristic city at sunset"


# ---------------------------------------------------------------------------
# generate_image_via_mws happy + error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_via_mws_returns_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/images/generations")
        body = request.read()
        assert b"qwen-image" in body
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "url": "https://imagegen.gpt.mws.ru/files/abc/img.png",
                        "b64_json": None,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        url, model = await generate_image_via_mws(
            http, settings=_mk_settings(), prompt="apple"
        )
    assert url.startswith("https://imagegen.gpt.mws.ru/")
    assert model == "qwen-image"


@pytest.mark.asyncio
async def test_generate_image_via_mws_handles_b64_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"url": None, "b64_json": "QUJDRA=="}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        url, _ = await generate_image_via_mws(
            http, settings=_mk_settings(), prompt="apple"
        )
    assert url.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_generate_image_raises_on_missing_credentials():
    async with httpx.AsyncClient() as http:
        with pytest.raises(ImageGenError):
            await generate_image_via_mws(
                http,
                settings=_mk_settings(mws_gpt_api_base=None, mws_gpt_api_key=None),
                prompt="apple",
            )


@pytest.mark.asyncio
async def test_generate_image_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": "bad gateway"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(ImageGenError):
            await generate_image_via_mws(
                http, settings=_mk_settings(), prompt="apple"
            )


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_build_image_chat_completion_embeds_markdown_image():
    out = build_image_chat_completion(
        model_label="gpt-hub",
        prompt="red apple",
        image_ref="https://x.test/img.png",
    )
    content = out["choices"][0]["message"]["content"]
    assert content.startswith("![red apple]")
    assert "https://x.test/img.png" in content
    assert out["object"] == "chat.completion"
