"""Outline / monolithic JSON parsing for ``SlidePlan.presentation_title``."""

from __future__ import annotations

import pytest

from gpthub_orchestrator.pptx.parse import parse_outline_plan_text, parse_slide_plan_text


def test_outline_parses_presentation_title() -> None:
    raw = (
        '{"presentation_title":"Моя презентация",'
        '"slides":[{"title":"Введение","kind":null},{"title":"Детали","kind":null}]}'
    )
    plan = parse_outline_plan_text(raw)
    assert plan.presentation_title == "Моя презентация"
    assert plan.slides[0].title == "Введение"


def test_monolithic_parses_presentation_title() -> None:
    raw = (
        '{"presentation_title":"Deck topic",'
        '"slides":[{"title":"S1","bullets":["a"],"notes":"","kind":null}]}'
    )
    plan = parse_slide_plan_text(raw)
    assert plan.presentation_title == "Deck topic"
    assert plan.slides[0].title == "S1"


def test_outline_without_presentation_title_raises() -> None:
    raw = '{"slides":[{"title":"A","kind":null}]}'
    with pytest.raises(ValueError, match="missing_presentation_title"):
        parse_outline_plan_text(raw)
