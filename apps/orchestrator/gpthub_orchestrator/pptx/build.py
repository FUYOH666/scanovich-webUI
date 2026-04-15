"""Build .pptx bytes from a validated SlidePlan (python-pptx)."""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from pathlib import Path

from gpthub_orchestrator.pptx.audience_templates import resolve_pptx_template_filename
from gpthub_orchestrator.pptx.schema import (
    MAX_BULLETS_PER_SLIDE,
    MAX_SLIDES,
    PptxGenError,
    SlidePlan,
    SlideSpec,
)
from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)

# python-pptx is the third-party package named ``pptx`` on sys.path (not this subpackage).
from pptx import Presentation  # type: ignore[import-untyped]
from pptx.enum.shapes import PP_PLACEHOLDER  # type: ignore[import-untyped]
from pptx.util import Pt  # type: ignore[import-untyped]

_MAX_TITLE_LEN = 200
_MAX_BULLET_LEN = 500
_MAX_NOTES_LEN = 4000

# Fallback order if layout names are missing (legacy).
_LAYOUT_PROBE_FALLBACK = (2, 3, 5, 1, 7, 0, 4, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)

# Prefer layouts that usually carry Slidesgo / business theme backgrounds (title + body).
_PREFERRED_LAYOUT_NAME_PARTS: tuple[str, ...] = (
    "TITLE_AND_BODY",
    "TWO_COLUMN",
    "ONE_COLUMN",
    "MAIN_POINT",
    "SECTION_HEADER",
    "SECTION_TITLE",
    "TITLE_ONLY",
    "CAPTION",
    "BIG_NUMBER",
    "TITLE",
    "BLANK",
    "CUSTOM",
)

# Титульный слайд (intro): всегда первый master layout в выбранном .pptx из assets — без probe и без участия LLM.
_INTRO_SLIDE_LAYOUT_INDEX = 0


def deck_title_for_intro(plan: SlidePlan) -> str:
    """Topic line for the opening slide: ``presentation_title`` if set, else first slide title."""
    pt = (plan.presentation_title or "").strip()
    if pt:
        return pt
    if not plan.slides:
        return "Presentation"
    return (plan.slides[0].title or "").strip() or "Presentation"


def _clip(s: str, max_len: int) -> str:
    t = (s or "").replace("\r", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _default_template_dirs() -> list[Path]:
    """Docker image path first, then repo `apps/orchestrator/assets/pttx`."""
    here = Path(__file__).resolve()
    orchestrator_root = here.parents[2]
    return [Path("/app/assets/pttx"), orchestrator_root / "assets" / "pttx"]


def _find_templates_dir(settings: Settings) -> Path | None:
    if not settings.pptx_asset_templates_enabled:
        return None
    raw = (settings.pptx_templates_dir or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    else:
        candidates.extend(_default_template_dirs())
    for d in candidates:
        if d.is_dir():
            files = sorted(d.glob("*.pptx"))
            if files:
                return d
    return None


def _pick_template_path(settings: Settings) -> Path | None:
    d = _find_templates_dir(settings)
    if not d:
        return None
    files = sorted(d.glob("*.pptx"))
    if not files:
        return None
    want_name = resolve_pptx_template_filename(settings.pptx_plan_audience)
    for p in files:
        if p.name == want_name:
            return p
    idx = settings.pptx_template_index % len(files)
    return files[idx]


def _delete_all_slides(prs: Presentation) -> None:
    while len(prs.slides) > 0:
        r_id = prs.slides._sldIdLst[0].rId
        prs.part.drop_rel(r_id)
        del prs.slides._sldIdLst[0]


def _layout_probe_sequence(
    prs: Presentation,
    *,
    preferred_name_parts: tuple[str, ...] | None = None,
) -> list[int]:
    """Order slide_layout indices: preferred name substrings first, then the rest."""
    parts = preferred_name_parts if preferred_name_parts is not None else _PREFERRED_LAYOUT_NAME_PARTS
    n = len(prs.slide_layouts)
    ordered: list[int] = []
    seen: set[int] = set()
    for part in parts:
        for i in range(n):
            if i in seen:
                continue
            try:
                nm = (prs.slide_layouts[i].name or "").upper()
            except Exception:  # noqa: BLE001
                nm = ""
            if part in nm:
                ordered.append(i)
                seen.add(i)
    for i in range(n):
        if i not in seen:
            ordered.append(i)
    if not ordered:
        ordered = list(range(n))
    return ordered


def _delete_last_slide(prs: Presentation) -> None:
    if len(prs.slides) == 0:
        return
    r_id = prs.slides._sldIdLst[-1].rId
    prs.part.drop_rel(r_id)
    del prs.slides._sldIdLst[-1]


def _body_text_frame(slide: object) -> object | None:
    for ph in slide.placeholders:  # type: ignore[attr-defined]
        try:
            pht = ph.placeholder_format.type
        except (ValueError, AttributeError):
            continue
        if pht in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT):
            return ph.text_frame
    for idx in (1, 2, 3):
        try:
            return slide.placeholders[idx].text_frame  # type: ignore[attr-defined]
        except (KeyError, IndexError, AttributeError):
            continue
    return None


def _apply_spec_to_slide(slide: object, spec: object) -> None:
    title_sh = slide.shapes.title  # type: ignore[attr-defined]
    if title_sh is None:
        raise PptxGenError("pptx_no_title_placeholder")
    title_sh.text = _clip(spec.title, _MAX_TITLE_LEN)  # type: ignore[attr-defined]

    tf = _body_text_frame(slide)
    bullets = spec.bullets[:MAX_BULLETS_PER_SLIDE]  # type: ignore[attr-defined]
    if tf is not None:
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
    elif bullets:
        extra = "\n" + "\n".join(f"• {_clip(b, _MAX_BULLET_LEN)}" for b in bullets)
        title_sh.text = _clip(spec.title + extra, 4000)  # type: ignore[attr-defined]

    notes_txt = _clip(spec.notes, _MAX_NOTES_LEN)  # type: ignore[attr-defined]
    if notes_txt:
        try:
            ns = slide.notes_slide  # type: ignore[attr-defined]
            ns.notes_text_frame.text = notes_txt
        except Exception as e:  # noqa: BLE001
            logger.warning("pptx_notes_skip err=%s", e)


def _probe_first_layout_index(
    prs: Presentation,
    spec: object,
    *,
    preferred_name_parts: tuple[str, ...] | None = None,
) -> int:
    n = len(prs.slide_layouts)
    sequence = _layout_probe_sequence(prs, preferred_name_parts=preferred_name_parts)
    for idx in sequence:
        if idx >= n:
            continue
        layout = prs.slide_layouts[idx]
        slide = prs.slides.add_slide(layout)
        try:
            _apply_spec_to_slide(slide, spec)
            return idx
        except (PptxGenError, AttributeError, IndexError, KeyError, ValueError) as e:
            logger.debug("pptx_layout_probe_skip idx=%s err=%s", idx, e)
            _delete_last_slide(prs)
    for idx in _LAYOUT_PROBE_FALLBACK:
        if idx >= n:
            continue
        if idx in sequence:
            continue
        layout = prs.slide_layouts[idx]
        slide = prs.slides.add_slide(layout)
        try:
            _apply_spec_to_slide(slide, spec)
            return idx
        except (PptxGenError, AttributeError, IndexError, KeyError, ValueError) as e:
            logger.debug("pptx_layout_probe_fallback_skip idx=%s err=%s", idx, e)
            _delete_last_slide(prs)
    raise PptxGenError("pptx_no_layout")


def _add_intro_slide_asset_layout(prs: Presentation, spec: SlideSpec) -> None:
    n = len(prs.slide_layouts)
    idx = _INTRO_SLIDE_LAYOUT_INDEX
    if idx < 0 or idx >= n:
        raise PptxGenError("pptx_intro_layout_index_invalid")
    slide = prs.slides.add_slide(prs.slide_layouts[idx])
    try:
        _apply_spec_to_slide(slide, spec)
    except (PptxGenError, AttributeError, IndexError, KeyError, ValueError) as e:
        _delete_last_slide(prs)
        raise PptxGenError("pptx_intro_layout_apply_failed") from e


def load_stripped_base_presentation(settings: Settings) -> Presentation:
    """Open template (or blank), remove all slides; ready for slide loop. I/O + parse — overlap with LLM."""
    path = _pick_template_path(settings)
    if path is None:
        tried = [
            str(p)
            for p in (
                [Path((settings.pptx_templates_dir or "").strip())]
                if (settings.pptx_templates_dir or "").strip()
                else _default_template_dirs()
            )
        ]
        logger.warning(
            "pptx_deck_blank_no_template enabled=%s dirs_checked=%s "
            "(rebuild orchestrator image so Dockerfile COPY apps/orchestrator/assets/pttx → /app/assets/pttx)",
            settings.pptx_asset_templates_enabled,
            tried,
        )
        return Presentation()
    try:
        prs = Presentation(str(path))
    except Exception as e:  # noqa: BLE001
        logger.warning("pptx_template_open_failed path=%s err=%s", path, e)
        return Presentation()
    logger.info(
        "pptx_deck_base_template file=%s path=%s slide_layouts=%s",
        path.name,
        path,
        len(prs.slide_layouts),
    )
    _delete_all_slides(prs)
    return prs


def build_pptx_from_plan(
    plan: SlidePlan,
    *,
    settings: Settings,
    base_prs: Presentation | None = None,
    on_slide_progress: Callable[[int, int], None] | None = None,
) -> bytes:
    if not plan.slides:
        raise PptxGenError("empty_plan")

    prs = base_prs if base_prs is not None else load_stripped_base_presentation(settings)

    specs: list[SlideSpec] = []
    if settings.pptx_intro_slide_enabled:
        specs.append(
            SlideSpec(title=deck_title_for_intro(plan), bullets=[], notes=""),
        )
    specs.extend(plan.slides[:MAX_SLIDES])

    n_total = len(specs)
    try:
        for i, spec in enumerate(specs):
            if settings.pptx_intro_slide_enabled and i == 0:
                _add_intro_slide_asset_layout(prs, spec)
            else:
                _probe_first_layout_index(prs, spec, preferred_name_parts=None)
            if on_slide_progress is not None:
                on_slide_progress(i + 1, n_total)
    except IndexError as e:
        raise PptxGenError("pptx_no_layout") from e

    bio = io.BytesIO()
    prs.save(bio)
    out = bio.getvalue()
    if not out.startswith(b"PK"):
        raise PptxGenError("pptx_not_zip")
    return out
