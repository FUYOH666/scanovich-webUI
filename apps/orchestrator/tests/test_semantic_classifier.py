"""Semantic task classifier (embedding prototypes) — mocked MWS."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from gpthub_orchestrator.semantic_classifier import (
    SEMANTIC_TASK_PROTOTYPES,
    _task_prototypes_for_embeddings,
    ambiguous_ru_exact_task_type,
    classify_messages_for_route,
)
from gpthub_orchestrator.settings import Settings

# Реплики и желаемый смысл маршрута (golden).
# Второй элемент — условная метка: pptx | image_gen | deep_research | simple_chat.
RU_USER_INTENT_SAMPLES: list[tuple[str, str]] = [
    ("бахни презу", "pptx"),
    ("сделай мне картинку слона", "image_gen"),
    ("делай картинку по презентации", "image_gen"),
    (
        "хорошо подумай. как вернуть данные сервера после падения",
        "deep_research",
    ),
    ("надоел. дай презу уже", "pptx"),
    ("верни картинку", "image_gen"),
    ("напиши описание презентации. ответь в чате", "simple_chat"),
    ("ты всё испортил. я хочу презу.", "pptx"),
    ("что-ты сгенерировал. в чат пиши.", "simple_chat"),
    ("как считаешь как стоит делать презентацию.", "simple_chat"),
    ("кинь презенташку", "pptx"),
    ("image хочу", "image_gen"),
    ("картинку слона хочу", "image_gen"),
    ("рисунок хочу", "image_gen"),
]


def _stub_vec(text: str, *, dim: int = 16) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    for i in range(dim):
        b = h[i % len(h)]
        out.append((b / 127.5) - 1.0)
    return out


def _coarse_to_semantic_task(coarse: str) -> str:
    return {
        "pptx": "pptx_generation",
        "image_gen": "image_generation",
        "deep_research": "deep_research",
        "simple_chat": "simple_chat",
        "user_help": "user_help",
    }[coarse]


def _first_prototype_phrase(semantic_task: str) -> str:
    protos = _task_prototypes_for_embeddings()[semantic_task]
    assert protos, f"no embedding prototypes for task {semantic_task!r}"
    return protos[0]


def _make_settings(**kw: object) -> Settings:
    base = {
        "litellm_base_url": "http://litellm.test",
        "orchestrator_api_key": "k",
        "mws_gpt_api_base": "https://api.test/v1",
        "mws_gpt_api_key": "mk",
        "classifier_semantic_enabled": True,
        "classifier_semantic_min_similarity": 0.25,
        "classifier_semantic_min_margin": 0.01,
    }
    base.update(kw)
    return Settings(**base)


def _make_settings_env_semantic(**kw: object) -> Settings:
    """Пороги как в прод-.env: CLASSIFIER_SEMANTIC_MIN_SIMILARITY=0.38, MIN_MARGIN=0.02."""
    base = {
        "litellm_base_url": "http://litellm.test",
        "orchestrator_api_key": "k",
        "mws_gpt_api_base": "https://api.test/v1",
        "mws_gpt_api_key": "mk",
        "classifier_semantic_enabled": True,
        "classifier_semantic_min_similarity": 0.38,
        "classifier_semantic_min_margin": 0.02,
        "classifier_semantic_override_locked_heuristic": False,
    }
    base.update(kw)
    return Settings(**base)


@pytest.mark.asyncio
async def test_semantic_disabled_returns_heuristic():
    s = _make_settings(classifier_semantic_enabled=False)
    messages = [{"role": "user", "content": "hello"}]
    async with httpx.AsyncClient() as http:
        out, src = await classify_messages_for_route(messages, s, http)
    assert src == "heuristic"
    assert out["task_type"] == "greeting_or_tiny"


@pytest.mark.asyncio
async def test_semantic_skips_when_image_in_message():
    s = _make_settings()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this"},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            ],
        }
    ]
    async with httpx.AsyncClient() as http:
        out, src = await classify_messages_for_route(messages, s, http)
    assert src == "heuristic"
    assert out["task_type"] in ("image_analysis", "multimodal_workflow")


@pytest.mark.asyncio
async def test_semantic_overrides_task_when_confident():
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    s = _make_settings()
    phrase = SEMANTIC_TASK_PROTOTYPES["code_help"][0]
    messages = [{"role": "user", "content": phrase}]

    async def fake_embed_texts(
        _http: httpx.AsyncClient,
        *,
        settings: Settings,
        texts: list[str],
    ) -> list[list[float]]:
        return [_stub_vec(t) for t in texts]

    async def fake_embed_one(
        _http: httpx.AsyncClient,
        *,
        settings: Settings,
        text: str,
    ) -> list[float]:
        return _stub_vec(text)

    async with httpx.AsyncClient() as http:
        with (
            patch("gpthub_orchestrator.semantic_classifier.embed_texts", side_effect=fake_embed_texts),
            patch("gpthub_orchestrator.semantic_classifier.embed_one", side_effect=fake_embed_one),
        ):
            out, src = await classify_messages_for_route(messages, s, http)

    assert src == "semantic"
    assert out["task_type"] == "code_help"
    assert "semantic_task_score" in out


@pytest.mark.asyncio
async def test_locked_heuristic_skips_semantic():
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    s = _make_settings()
    messages = [{"role": "user", "content": "Привет"}]

    async with httpx.AsyncClient() as http:
        with patch("gpthub_orchestrator.semantic_classifier.embed_texts", new_callable=AsyncMock) as em:
            out, src = await classify_messages_for_route(messages, s, http)
    em.assert_not_called()
    assert src == "heuristic"
    assert out["task_type"] == "greeting_or_tiny"


@pytest.mark.parametrize(
    "threshold_profile",
    [
        pytest.param("dev", id="thresholds_0.25_0.01"),
        pytest.param("env", id="thresholds_env_0.38_0.02"),
    ],
)
@pytest.mark.parametrize(("text", "expected_coarse"), RU_USER_INTENT_SAMPLES)
@pytest.mark.asyncio
async def test_ru_user_intent_samples_with_semantic_enabled(
    text: str,
    expected_coarse: str,
    threshold_profile: str,
) -> None:
    """При включённой семантике: ``ambiguous_ru`` или ``semantic``; пороги dev и как в .env."""
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    expected_task = _coarse_to_semantic_task(expected_coarse)
    s = _make_settings() if threshold_profile == "dev" else _make_settings_env_semantic()
    messages = [{"role": "user", "content": text}]

    async with httpx.AsyncClient() as http:
        if ambiguous_ru_exact_task_type(text) is not None:
            out, src = await classify_messages_for_route(messages, s, http)
            assert src == "ambiguous_ru", (text, src, out.get("task_type"))
            assert out["task_type"] == expected_task
        else:

            async def fake_embed_texts(
                _http: httpx.AsyncClient,
                *,
                settings: Settings,
                texts: list[str],
            ) -> list[list[float]]:
                return [_stub_vec(t) for t in texts]

            anchor = _first_prototype_phrase(expected_task)

            async def fake_embed_one(
                _http: httpx.AsyncClient,
                *,
                settings: Settings,
                text: str,
            ) -> list[float]:
                _ = text
                return _stub_vec(anchor)

            with (
                patch("gpthub_orchestrator.semantic_classifier.embed_texts", side_effect=fake_embed_texts),
                patch("gpthub_orchestrator.semantic_classifier.embed_one", side_effect=fake_embed_one),
            ):
                out, src = await classify_messages_for_route(messages, s, http)

            assert src == "semantic", (threshold_profile, text, src, out.get("task_type"))
            assert out["task_type"] == expected_task, (threshold_profile, text, out["task_type"])
            assert "semantic_task_score" in out
