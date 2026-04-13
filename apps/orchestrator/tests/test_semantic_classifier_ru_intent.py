"""Golden RU-реплики: один прогон classify_messages_for_route на каждую фразу.

Несовпадения с golden дают :class:`UserWarning`, тест не падает (смок маршрутизации под SHA-stub).
"""

from __future__ import annotations

import hashlib
import warnings
from unittest.mock import patch

import httpx
import pytest

from gpthub_orchestrator.semantic_classifier import ambiguous_ru_exact_task_type, classify_messages_for_route
from gpthub_orchestrator.settings import Settings

# Реплики и желаемый смысл: pptx | image_gen | deep_research | simple_chat.
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
    ("дай рисунок пельменя", "image_gen"),
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


def _warn_unless(condition: bool, message: str) -> None:
    if not condition:
        warnings.warn(message, UserWarning, stacklevel=2)


@pytest.mark.parametrize(("text", "expected_coarse"), RU_USER_INTENT_SAMPLES)
@pytest.mark.asyncio
async def test_ru_user_intent_samples(text: str, expected_coarse: str) -> None:
    import gpthub_orchestrator.semantic_classifier as sem

    sem._proto_cache = None
    expected_task = _coarse_to_semantic_task(expected_coarse)
    s = _make_settings()
    messages = [{"role": "user", "content": text}]

    async with httpx.AsyncClient() as http:
        if ambiguous_ru_exact_task_type(text) is not None:
            out, src = await classify_messages_for_route(messages, s, http)
            _warn_unless(
                src == "ambiguous_ru",
                f"RU golden: expected ambiguous_ru, got src={src!r} task={out.get('task_type')!r} text={text!r}",
            )
            _warn_unless(
                out["task_type"] == expected_task,
                f"RU golden: expected task_type={expected_task!r}, got {out.get('task_type')!r} text={text!r}",
            )
        else:
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

            with (
                patch("gpthub_orchestrator.semantic_classifier.embed_texts", side_effect=fake_embed_texts),
                patch("gpthub_orchestrator.semantic_classifier.embed_one", side_effect=fake_embed_one),
            ):
                out, src = await classify_messages_for_route(messages, s, http)

            _warn_unless(
                src == "semantic",
                f"RU golden: expected semantic, got src={src!r} task={out.get('task_type')!r} text={text!r}",
            )
            _warn_unless(
                out["task_type"] == expected_task,
                f"RU golden: expected task_type={expected_task!r}, got {out.get('task_type')!r} text={text!r}",
            )
            _warn_unless(
                "semantic_task_score" in out,
                f"RU golden: missing semantic_task_score src={src!r} text={text!r}",
            )
