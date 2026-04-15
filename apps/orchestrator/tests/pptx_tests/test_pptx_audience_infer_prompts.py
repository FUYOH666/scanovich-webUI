"""Prompt wording → ``pptx_plan_audience`` inference (heuristic, no LLM).

These tests lock the mapping from typical user phrases (RU/EN) to template audience keys used in slide-plan prompts and ``*.pptx`` selection.
"""

from __future__ import annotations

import pytest

from gpthub_orchestrator.pptx.audience_infer import (
    infer_pptx_plan_audience_from_messages,
    resolve_effective_pptx_plan_audience,
)
from gpthub_orchestrator.settings import Settings


def _msg(role: str, content: str) -> dict[str, str]:
    return {"role": role, "content": content}


@pytest.mark.parametrize(
    ("user_text", "expected"),
    [
        ("Сделай для инвесторов презентацию возможностей МТС в AI эру", "investor"),
        ("Pitch deck for investors about our SaaS metrics", "investor"),
        ("Презентация для венчурных фондов", "investor"),
        ("VC audience — один слайд про runway", "investor"),
        ("Доклад для студентов про ML", "education"),
        ("School presentation about photosynthesis", "education"),
        ("University workshop on ethics", "education"),
        ("Tutorial for beginners: Python", "education"),
        ("Презентация для дизайнеров про рекламу", "creative"),
        ("Creative portfolio review for the team", "creative"),
        ("Креативная подача бренда", "creative"),
        ("Деловая презентация для руководства", "business"),
        ("B2B deck for corporate stakeholders", "business"),
        ("Коммерческое предложение для бизнеса", "business"),
        ("Презентация для широкой аудитории о продукте", "general"),
        ("Mass market overview slide", "general"),
    ],
)
def test_infer_audience_from_single_user_message(user_text: str, expected: str) -> None:
    messages = [_msg("user", user_text)]
    assert infer_pptx_plan_audience_from_messages(messages) == expected


@pytest.mark.parametrize(
    "user_text",
    [
        "Сгенерируй презентацию про котиков",
        "Make slides about Q3 roadmap",
        "Just a few bullet points on Kubernetes",
    ],
)
def test_infer_returns_none_when_no_audience_cue(user_text: str) -> None:
    assert infer_pptx_plan_audience_from_messages([_msg("user", user_text)]) is None


def test_infer_uses_latest_user_turn_in_thread() -> None:
    messages = [
        _msg("user", "Презентация для студентов"),
        _msg("assistant", "Ок."),
        _msg("user", "Переделай: теперь для инвесторов, коротко"),
    ]
    assert infer_pptx_plan_audience_from_messages(messages) == "investor"


def test_infer_investor_wins_over_business_in_same_message() -> None:
    text = "Для инвесторов и бизнес-партнёров: одна презентация"
    assert infer_pptx_plan_audience_from_messages([_msg("user", text)]) == "investor"


def test_resolve_falls_back_to_settings_default() -> None:
    messages = [_msg("user", "Презентация без явной аудитории")]
    s = Settings(
        litellm_base_url="http://x",
        orchestrator_api_key="k",
        pptx_plan_audience="education",
    )
    assert (
        resolve_effective_pptx_plan_audience(
            messages,
            default_audience=s.pptx_plan_audience,
        )
        == "education"
    )


def test_resolve_overrides_default_when_infer_matches() -> None:
    messages = [_msg("user", "Только для инвесторов")]
    s = Settings(
        litellm_base_url="http://x",
        orchestrator_api_key="k",
        pptx_plan_audience="education",
    )
    assert (
        resolve_effective_pptx_plan_audience(
            messages,
            default_audience=s.pptx_plan_audience,
        )
        == "investor"
    )
