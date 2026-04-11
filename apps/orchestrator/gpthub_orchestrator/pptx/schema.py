"""Pydantic models for slide-plan JSON."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_SLIDES = 20
MAX_BULLETS_PER_SLIDE = 8


class PptxGenError(Exception):
    """Slide-plan LLM or deck build failure (caller may fall back to plain text)."""


class SlideSpec(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = ""
    bullets: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("bullets", mode="before")
    @classmethod
    def _coerce_bullets(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            out: list[str] = []
            for x in v:
                s = str(x).strip()
                if s:
                    out.append(s)
            return out
        return []


class SlidePlan(BaseModel):
    slides: list[SlideSpec] = Field(default_factory=list)

    @field_validator("slides", mode="before")
    @classmethod
    def _coerce_slides(cls, v: object) -> list[object]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return v[:MAX_SLIDES]
