"""Tests for ``pptx.response`` markdown helpers."""

from __future__ import annotations

from gpthub_orchestrator.pptx import markdown_preview_with_download_link
from gpthub_orchestrator.pptx.schema import SlidePlan, SlideSpec


def test_markdown_preview_shows_kind() -> None:
    plan = SlidePlan(
        slides=[SlideSpec(title="T", bullets=["a"], notes="", kind="bullets")],
    )
    md = markdown_preview_with_download_link(plan, "https://example.test/d.pptx?token=x")
    assert "макет: `bullets`" in md


def test_markdown_preview_intro_line() -> None:
    plan = SlidePlan(
        slides=[SlideSpec(title="Тема", bullets=["a"], notes="")],
    )
    md = markdown_preview_with_download_link(
        plan, "https://example.test/d.pptx?token=x", intro_title="Тема"
    )
    assert "Титульный слайд" in md
    assert "Тема" in md
