"""Pydantic models for slide-plan JSON."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_SLIDES = 20
MAX_BULLETS_PER_SLIDE = 8

# Semantic layout tags (inspired by presentation-ai DEFAULT_LAYOUTS); optional per slide.
ALLOWED_SLIDE_KINDS: frozenset[str] = frozenset(
    {
        "bullets",
        "columns",
        "icons",
        "cycle",
        "arrows",
        "arrow_vertical",
        "timeline",
        "pyramid",
        "staircase",
        "boxes",
        "compare",
        "before_after",
        "pros_cons",
        "table",
        "charts",
        "stats",
    }
)


class PptxGenError(Exception):
    """Slide-plan LLM or deck build failure (caller may fall back to plain text)."""


def normalize_slide_kind(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower().replace("-", "_")
    if not s or s in ("auto", "general"):
        return None
    if s == "arrowvertical":
        s = "arrow_vertical"
    if s == "beforeafter":
        s = "before_after"
    if s == "proscons":
        s = "pros_cons"
    if s in ALLOWED_SLIDE_KINDS:
        return s
    return None


class SlideSpec(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = ""
    bullets: list[str] = Field(default_factory=list)
    notes: str = ""
    kind: str | None = Field(
        default=None,
        description="Optional layout intent (see ALLOWED_SLIDE_KINDS); file build may still use one template.",
    )

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, v: object) -> str | None:
        return normalize_slide_kind(v)

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
