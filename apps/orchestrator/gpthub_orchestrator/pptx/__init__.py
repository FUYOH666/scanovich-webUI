"""PPTX slide-plan LLM + deck build (WOW-3)."""

from __future__ import annotations

from gpthub_orchestrator.pptx.build import build_pptx_from_plan, load_stripped_base_presentation
from gpthub_orchestrator.pptx.parse import extract_json_object, parse_slide_plan_text
from gpthub_orchestrator.pptx.plan import request_slide_plan
from gpthub_orchestrator.pptx.response import (
    build_pptx_artifact_download_url,
    build_pptx_chat_completion,
    build_pptx_error_chat_completion,
    build_pptx_error_sse_chunks,
    build_pptx_sse_chunks,
    markdown_preview_with_download_link,
    pptx_download_filename,
)
from gpthub_orchestrator.pptx.schema import (
    ALLOWED_SLIDE_KINDS,
    MAX_BULLETS_PER_SLIDE,
    MAX_SLIDES,
    PptxGenError,
    SlidePlan,
    SlideSpec,
)

__all__ = [
    "ALLOWED_SLIDE_KINDS",
    "MAX_BULLETS_PER_SLIDE",
    "MAX_SLIDES",
    "PptxGenError",
    "SlidePlan",
    "SlideSpec",
    "build_pptx_artifact_download_url",
    "build_pptx_chat_completion",
    "build_pptx_error_chat_completion",
    "build_pptx_error_sse_chunks",
    "build_pptx_from_plan",
    "build_pptx_sse_chunks",
    "load_stripped_base_presentation",
    "extract_json_object",
    "markdown_preview_with_download_link",
    "parse_slide_plan_text",
    "pptx_download_filename",
    "request_slide_plan",
]
