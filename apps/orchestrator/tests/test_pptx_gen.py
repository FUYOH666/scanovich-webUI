"""Tests for PPTX intent helpers in ``pptx_gen`` (pipeline lives in ``gpthub_orchestrator.pptx``)."""

from __future__ import annotations

import pytest

from gpthub_orchestrator.pptx_gen import extract_pptx_topic, is_pptx_request
from gpthub_orchestrator.settings import Settings


def _mk_settings(**over):
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
        "/pptx RAG в продакшене",
        "/slides MLOps стек",
        "Сделай презентацию по архитектуре нашей системы",
        "Создай презентацию о трендах LLM 2026",
        "Подготовь презентацию на тему feature store",
        "Презентация про vector databases",
        "Слайды по нашему MVP",
        "make a presentation about transformer scaling",
        "build a deck on enterprise RAG",
        "create slides for our roadmap",
        "powerpoint about AI safety",
        "давай, в формате pptx будет? создай",
        "сделай в формате pptx",
        "в pptx формате собери",
    ],
)
def test_is_pptx_request_positive(text: str) -> None:
    assert is_pptx_request(text)


@pytest.mark.parametrize(
    "text",
    [
        "Как работает RAG в двух предложениях",
        "Напиши код для feature store на Python",
        "Нарисуй схему архитектуры",
        "Привет!",
        "",
        "x" * 9000,
        "Расскажи про презентационные навыки",  # noun without verb context
    ],
)
def test_is_pptx_request_negative(text: str) -> None:
    assert not is_pptx_request(text)


def test_extract_pptx_topic_strips_slash() -> None:
    assert extract_pptx_topic("/pptx vector databases") == "vector databases"
    assert extract_pptx_topic("/slides MLOps стек") == "MLOps стек"


def test_extract_pptx_topic_passthrough() -> None:
    q = "Сделай презентацию по архитектуре нашей системы"
    assert extract_pptx_topic(q) == q


# ---------------------------------------------------------------------------
# Classifier + router wiring (integration)
# ---------------------------------------------------------------------------


def test_classifier_routes_pptx_intent_to_pptx_task() -> None:
    from gpthub_orchestrator.classifier import classify_messages

    msgs = [{"role": "user", "content": "Сделай презентацию по архитектуре нашей системы"}]
    out = classify_messages(msgs)
    assert out["task_type"] == "pptx_generation"


def test_classifier_normal_message_is_not_pptx() -> None:
    from gpthub_orchestrator.classifier import classify_messages

    msgs = [{"role": "user", "content": "Расскажи про vector databases"}]
    out = classify_messages(msgs)
    assert out["task_type"] != "pptx_generation"


def test_router_pptx_fallback_when_council_disabled() -> None:
    from gpthub_orchestrator.router import choose_model

    s = _mk_settings()
    classification = {"modalities": ["text"], "task_type": "pptx_generation"}
    out = choose_model(classification, s)
    assert out["reason"] == "pptx_generation_fallback"
