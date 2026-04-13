"""Tests for ``pptx.parse`` — JSON extraction, slide plan parsing, visible clamp."""

from __future__ import annotations

import json

from gpthub_orchestrator.pptx import extract_json_object, parse_slide_plan_text
from gpthub_orchestrator.pptx.parse import (
    SLIDE_AGENT_MAX_VISIBLE_CHARS,
    clamp_slide_visible_to_max,
)
from gpthub_orchestrator.pptx.schema import SlideSpec


def test_extract_json_object_fence() -> None:
    raw = 'Sure\n```json\n{"slides":[]}\n```\n'
    assert '"slides"' in extract_json_object(raw)


def test_parse_slide_plan_text_minimal() -> None:
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
    assert plan.slides[0].kind is None


def test_parse_slide_plan_text_with_kind() -> None:
    text = json.dumps(
        {
            "slides": [
                {"title": "Roadmap", "bullets": ["Q1"], "notes": "", "kind": "timeline"},
            ]
        }
    )
    plan = parse_slide_plan_text(text)
    assert plan.slides[0].kind == "timeline"


def test_parse_slide_plan_text_invalid_kind_dropped() -> None:
    text = json.dumps(
        {
            "slides": [
                {"title": "X", "bullets": [], "notes": "", "kind": "not-a-real-layout"},
            ]
        }
    )
    plan = parse_slide_plan_text(text)
    assert plan.slides[0].kind is None


def test_clamp_slide_visible_drops_bullets_from_end_until_under_cap() -> None:
    """Whole bullets removed from the tail until title + bullets ≤ max."""
    title = "T" * 50
    bullets = ["x" * 100, "y" * 100, "z" * 100, "w" * 100, "last" * 20]
    spec = SlideSpec(title=title, bullets=bullets, notes="keep", kind="bullets")
    out = clamp_slide_visible_to_max(spec, max_chars=SLIDE_AGENT_MAX_VISIBLE_CHARS)
    assert out.notes == "keep"
    assert out.kind == "bullets"
    total = len(out.title) + sum(len(b) for b in out.bullets)
    assert total <= SLIDE_AGENT_MAX_VISIBLE_CHARS
    assert len(out.bullets) < len(bullets)


def test_clamp_slide_visible_truncates_last_bullet_when_one_remains() -> None:
    """Single long line without spaces: last resort is a prefix cap."""
    title = "Hi"
    long_bullet = "B" * 600
    spec = SlideSpec(title=title, bullets=[long_bullet], notes="", kind=None)
    out = clamp_slide_visible_to_max(spec, max_chars=SLIDE_AGENT_MAX_VISIBLE_CHARS)
    assert len(out.title) + sum(len(b) for b in out.bullets) <= SLIDE_AGENT_MAX_VISIBLE_CHARS
    want = SLIDE_AGENT_MAX_VISIBLE_CHARS - len(title)
    assert out.bullets == [long_bullet[:want]]


def test_clamp_slide_visible_truncates_long_line_at_word_boundary() -> None:
    title = "X"
    words = "word " * 300
    spec = SlideSpec(title=title, bullets=[words], notes="", kind=None)
    out = clamp_slide_visible_to_max(spec)
    b = out.bullets[0]
    assert len(title) + len(b) <= SLIDE_AGENT_MAX_VISIBLE_CHARS
    assert b.strip()
    assert not b.endswith("wo")
    assert b.endswith(" ") or b.endswith("word")


def test_clamp_slide_visible_drops_trailing_lines_in_bullet() -> None:
    """Newlines separate lines; trailing whole lines are removed before mid-line cuts."""
    title = "T"
    bullet = "first line short\n" + ("second " * 120) + "\n" + "third should drop entirely"
    spec = SlideSpec(title=title, bullets=[bullet], notes="", kind=None)
    out = clamp_slide_visible_to_max(spec)
    assert "third should drop" not in out.bullets[0]
    assert len(title) + len(out.bullets[0]) <= SLIDE_AGENT_MAX_VISIBLE_CHARS


def test_clamp_slide_visible_truncates_title_when_no_bullets() -> None:
    long_title = "N" * 600
    spec = SlideSpec(title=long_title, bullets=[], notes="", kind=None)
    out = clamp_slide_visible_to_max(spec)
    assert out.title == long_title[:SLIDE_AGENT_MAX_VISIBLE_CHARS]
    assert out.bullets == []


def test_clamp_slide_visible_title_priority_when_budget_exhausted() -> None:
    """If title alone exceeds remaining budget with one bullet, title wins (bullet dropped)."""
    title = "T" * 520
    spec = SlideSpec(title=title, bullets=["extra"], notes="", kind=None)
    out = clamp_slide_visible_to_max(spec)
    assert out.title == title[:SLIDE_AGENT_MAX_VISIBLE_CHARS]
    assert out.bullets == []


def test_clamp_slide_visible_unchanged_when_already_short() -> None:
    spec = SlideSpec(title="A", bullets=["b", "c"], notes="n", kind="stats")
    out = clamp_slide_visible_to_max(spec)
    assert out == spec
