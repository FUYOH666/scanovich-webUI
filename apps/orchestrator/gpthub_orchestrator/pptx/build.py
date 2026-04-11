"""Build .pptx bytes from a validated SlidePlan (python-pptx)."""

from __future__ import annotations

import io
import logging

from gpthub_orchestrator.pptx.schema import (
    MAX_BULLETS_PER_SLIDE,
    MAX_SLIDES,
    PptxGenError,
    SlidePlan,
)

logger = logging.getLogger(__name__)

# python-pptx is the third-party package named ``pptx`` on sys.path (not this subpackage).
from pptx import Presentation  # type: ignore[import-untyped]
from pptx.util import Pt  # type: ignore[import-untyped]

_MAX_TITLE_LEN = 200
_MAX_BULLET_LEN = 500
_MAX_NOTES_LEN = 4000


def _clip(s: str, max_len: int) -> str:
    t = (s or "").replace("\r", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def build_pptx_from_plan(plan: SlidePlan) -> bytes:
    if not plan.slides:
        raise PptxGenError("empty_plan")

    prs = Presentation()
    try:
        layout = prs.slide_layouts[1]
    except IndexError as e:
        raise PptxGenError("pptx_no_layout") from e

    for spec in plan.slides[:MAX_SLIDES]:
        slide = prs.slides.add_slide(layout)
        title_sh = slide.shapes.title
        body = slide.placeholders[1]
        tf = body.text_frame
        title_sh.text = _clip(spec.title, _MAX_TITLE_LEN)

        bullets = spec.bullets[:MAX_BULLETS_PER_SLIDE]
        tf.clear()
        if not bullets:
            p0 = tf.paragraphs[0]
            p0.text = ""
            p0.level = 0
        else:
            for i, bullet in enumerate(bullets):
                line = _clip(bullet, _MAX_BULLET_LEN)
                if i == 0:
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                p.text = line
                p.level = 0
                try:
                    p.font.size = Pt(18)
                except Exception:  # noqa: BLE001
                    logger.debug("pptx_bullet_font_skip")

        notes_txt = _clip(spec.notes, _MAX_NOTES_LEN)
        if notes_txt:
            try:
                ns = slide.notes_slide
                ns.notes_text_frame.text = notes_txt
            except Exception as e:  # noqa: BLE001
                logger.warning("pptx_notes_skip err=%s", e)

    bio = io.BytesIO()
    prs.save(bio)
    out = bio.getvalue()
    if not out.startswith(b"PK"):
        raise PptxGenError("pptx_not_zip")
    return out
