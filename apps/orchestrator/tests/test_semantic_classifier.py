"""Semantic task classifier (embedding prototypes) — mocked MWS."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from gpthub_orchestrator.semantic_classifier import (
    SEMANTIC_TASK_PROTOTYPES,
    classify_messages_for_route,
    clean_user_text_for_semantic_routing,
)
from gpthub_orchestrator.settings import Settings


def _stub_vec(text: str, *, dim: int = 16) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    for i in range(dim):
        b = h[i % len(h)]
        out.append((b / 127.5) - 1.0)
    return out


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
async def test_semantic_embedding_includes_transcript_artifacts():
    """Placeholder-only user text + ingest transcript: embed the spoken question."""
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    s = _make_settings()
    messages = [{"role": "user", "content": "Прикреплённые документы: transcript — 1"}]
    artifacts = [
        {"type": "transcript", "title": "Recording.wav", "content": "What is the capital of France?"},
    ]
    captured: dict[str, str] = {}

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
        captured["text"] = text
        return _stub_vec(text)

    async with httpx.AsyncClient() as http:
        with (
            patch("gpthub_orchestrator.semantic_classifier.embed_texts", side_effect=fake_embed_texts),
            patch("gpthub_orchestrator.semantic_classifier.embed_one", side_effect=fake_embed_one),
        ):
            _out, _src = await classify_messages_for_route(
                messages, s, http, ingest_artifacts=artifacts
            )

    assert "France" in captured.get("text", "")


@pytest.mark.parametrize(
    "override_locked",
    [pytest.param(False, id="override_false"), pytest.param(True, id="override_true")],
)
@pytest.mark.asyncio
async def test_locked_heuristic_semantic_respects_override_flag(override_locked: bool) -> None:
    """``CLASSIFIER_SEMANTIC_OVERRIDE_LOCKED_HEURISTIC``: False — замок; True — семантика может перебить greeting."""
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    s = _make_settings(classifier_semantic_override_locked_heuristic=override_locked)
    messages = [{"role": "user", "content": "Привет"}]

    anchor = SEMANTIC_TASK_PROTOTYPES["code_help"][0]

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
        _ = text
        return _stub_vec(anchor)

    async with httpx.AsyncClient() as http:
        with patch("gpthub_orchestrator.semantic_classifier.embed_texts", new_callable=AsyncMock) as em_texts:
            if override_locked:
                em_texts.side_effect = fake_embed_texts
                with patch(
                    "gpthub_orchestrator.semantic_classifier.embed_one",
                    side_effect=fake_embed_one,
                ):
                    out, src = await classify_messages_for_route(messages, s, http)
            else:
                out, src = await classify_messages_for_route(messages, s, http)

    if not override_locked:
        em_texts.assert_not_called()
        assert src == "heuristic"
        assert out["task_type"] == "greeting_or_tiny"
    else:
        em_texts.assert_called()
        assert src == "semantic"
        assert out["task_type"] == "code_help"
        assert "semantic_task_score" in out


@pytest.mark.parametrize(
    "threshold_profile",
    [
        pytest.param("dev", id="thresholds_0.25_0.01"),
        pytest.param("env", id="thresholds_env_0.38_0.02"),
    ],
)
@pytest.mark.asyncio
async def test_override_locked_true_matches_env_semantic_thresholds(threshold_profile: str) -> None:
    """Прод-флаги: semantic on + ``CLASSIFIER_SEMANTIC_OVERRIDE_LOCKED_HEURISTIC=true`` — замок снят."""
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    kw = dict(classifier_semantic_override_locked_heuristic=True)
    s = (
        _make_settings(**kw)
        if threshold_profile == "dev"
        else _make_settings_env_semantic(**kw)
    )
    messages = [{"role": "user", "content": "Привет"}]
    anchor = SEMANTIC_TASK_PROTOTYPES["code_help"][0]

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
        _ = text
        return _stub_vec(anchor)

    async with httpx.AsyncClient() as http:
        with (
            patch("gpthub_orchestrator.semantic_classifier.embed_texts", side_effect=fake_embed_texts),
            patch("gpthub_orchestrator.semantic_classifier.embed_one", side_effect=fake_embed_one),
        ):
            out, src = await classify_messages_for_route(messages, s, http)

    assert src == "semantic"
    assert out["task_type"] == "code_help"
    assert s.classifier_semantic_override_locked_heuristic is True


def test_clean_user_text_strips_chat_history_block() -> None:
    raw = (
        "Самый счастливый человек это кто\n\n"
        "<chat_history>\n"
        "USER: Сгенерируй картинку кота\n"
        "ASSISTANT: ок\n"
        "</chat_history>"
    )
    cleaned = clean_user_text_for_semantic_routing(raw)
    assert cleaned == "Самый счастливый человек это кто"
    assert "картинку" not in cleaned


@pytest.mark.asyncio
async def test_semantic_skips_open_webui_synthetic_user_prompt() -> None:
    """Follow-up / title-style blobs must not call embeddings."""
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    s = _make_settings()
    blob = (
        "### Task:\n"
        "Suggest 3-5 relevant follow-up questions or prompts that the user might naturally ask next\n"
        "### Chat History:\n<chat_history>\nUSER: hello\nASSISTANT: hi\n</chat_history>\n"
    )
    messages = [{"role": "user", "content": blob}]
    async with httpx.AsyncClient() as http:
        with patch("gpthub_orchestrator.semantic_classifier.embed_one", new_callable=AsyncMock) as em_one:
            with patch("gpthub_orchestrator.semantic_classifier.embed_texts", new_callable=AsyncMock) as em_texts:
                out, src = await classify_messages_for_route(messages, s, http)
    em_one.assert_not_called()
    em_texts.assert_not_called()
    assert src == "heuristic"
    assert out["task_type"] == "simple_chat"


@pytest.mark.asyncio
async def test_semantic_embedding_sees_clean_line_not_history() -> None:
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    s = _make_settings()
    phrase = SEMANTIC_TASK_PROTOTYPES["code_help"][0]
    raw = f"{phrase}\n\n<chat_history>\nUSER: нарисуй слона\n</chat_history>"
    messages = [{"role": "user", "content": raw}]

    async def fake_embed_texts(
        _http: httpx.AsyncClient,
        *,
        settings: Settings,
        texts: list[str],
    ) -> list[list[float]]:
        return [_stub_vec(t) for t in texts]

    seen: list[str] = []

    async def fake_embed_one(
        _http: httpx.AsyncClient,
        *,
        settings: Settings,
        text: str,
    ) -> list[float]:
        seen.append(text)
        return _stub_vec(text)

    async with httpx.AsyncClient() as http:
        with (
            patch("gpthub_orchestrator.semantic_classifier.embed_texts", side_effect=fake_embed_texts),
            patch("gpthub_orchestrator.semantic_classifier.embed_one", side_effect=fake_embed_one),
        ):
            out, src = await classify_messages_for_route(messages, s, http)

    assert src == "semantic"
    assert seen and seen[0] == phrase
    assert "слона" not in seen[0]
    assert out["task_type"] == "code_help"
