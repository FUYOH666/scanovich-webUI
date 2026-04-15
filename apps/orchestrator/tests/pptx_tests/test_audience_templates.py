"""Audience → bundled template filename mapping."""

from __future__ import annotations

from gpthub_orchestrator.pptx.audience_templates import (
    normalize_pptx_plan_audience,
    resolve_pptx_template_filename,
)
from gpthub_orchestrator.settings import Settings


def test_normalize_teacher_student_are_unknown() -> None:
    assert normalize_pptx_plan_audience("teacher") == "auto"
    assert normalize_pptx_plan_audience("STUDENT") == "auto"


def test_normalize_unknown_becomes_auto() -> None:
    assert normalize_pptx_plan_audience("nope") == "auto"


def test_resolve_filenames() -> None:
    assert resolve_pptx_template_filename("general") == "dark.pptx"
    assert resolve_pptx_template_filename("auto") == "dark.pptx"
    assert resolve_pptx_template_filename("business") == "business.pptx"
    assert resolve_pptx_template_filename("investor") == "investor.pptx"
    assert resolve_pptx_template_filename("education") == "education.pptx"
    assert resolve_pptx_template_filename("creative") == "creative.pptx"


def test_settings_invalid_audience_becomes_auto() -> None:
    s = Settings(
        litellm_base_url="http://x",
        orchestrator_api_key="k",
        pptx_plan_audience="teacher",
    )
    assert s.pptx_plan_audience == "auto"
