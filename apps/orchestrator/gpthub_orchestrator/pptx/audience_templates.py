"""Bundled ``assets/pttx/*.pptx`` selection by ``pptx_plan_audience``."""

from __future__ import annotations

from typing import Final

# Filenames must match files under apps/orchestrator/assets/pttx (and /app/assets/pttx in Docker).
PPTX_TEMPLATE_FILENAME_BY_AUDIENCE: Final[dict[str, str]] = {
    "auto": "dark.pptx",
    "general": "dark.pptx",
    "business": "business.pptx",
    "investor": "investor.pptx",
    "education": "education.pptx",
    "creative": "creative.pptx",
}

PPTX_PLAN_AUDIENCE_VALUES: Final[frozenset[str]] = frozenset(PPTX_TEMPLATE_FILENAME_BY_AUDIENCE.keys())


def normalize_pptx_plan_audience(raw: object) -> str:
    """Lowercase; clamp unknown values to ``auto``."""
    if raw is None:
        return "auto"
    s = str(raw).strip().lower()
    if not s:
        return "auto"
    if s not in PPTX_PLAN_AUDIENCE_VALUES:
        return "auto"
    return s


def resolve_pptx_template_filename(audience: str) -> str:
    """Return ``*.pptx`` basename for a normalized audience key."""
    key = normalize_pptx_plan_audience(audience)
    return PPTX_TEMPLATE_FILENAME_BY_AUDIENCE[key]
