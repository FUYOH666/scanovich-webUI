#!/usr/bin/env python3
"""Build docs/submission/GPTHub_architecture_submission.pdf for hackathon upload.

Страницы 1–3: структурированный текст (кириллица с нормальным ToUnicode в PDF) +
две схемы PNG (для людей и vision-моделей).

Страницы 4+: приложение — полный текст Mermaid из architecture.mmd и user_flow.mmd
моноширинным шрифтом, чтобы **текстовое извлечение** из PDF (pypdf/pdfminer) давало
граф для ИИ-жюри без OCR по растру.

Run from repo root:
  uv run --with reportlab --with pillow python scripts/build_submission_architecture_pdf.py
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)

logger = logging.getLogger("build_submission_architecture_pdf")

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "docs" / "submission"
DEFAULT_OUT = SUB / "GPTHub_architecture_submission.pdf"
MERMAID_CHUNK_LINES = 52
MAX_LINE_LEN = 98


def _pick_cyrillic_ttf() -> Path | None:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _register_fonts() -> tuple[str, str]:
    """Return (body_font, bold_name) — bold may map to same if no separate file."""
    ttf = _pick_cyrillic_ttf()
    if ttf is not None:
        pdfmetrics.registerFont(TTFont("GPTHubBody", str(ttf)))
        logger.info("registered Cyrillic font: %s", ttf)
        return "GPTHubBody", "GPTHubBody"
    logger.warning("no Cyrillic TTF found; body text may miss glyphs")
    return "Helvetica", "Helvetica-Bold"


def _xmlescape(s: str) -> str:
    return escape(s, entities={'"': "&quot;", "'": "&apos;"})


def _parse_submission_txt(raw: str) -> tuple[str, list[tuple[str, str | list[str]]]]:
    """Return (document_title, list of ('h', text) or ('p', text) or ('bullets', [..]))."""
    lines = raw.splitlines()
    doc_title = "GPTHub Prod — архитектура и User Flow"
    sections: list[tuple[str, str | list[str]]] = []
    current_h: str | None = None
    bullets: list[str] = []
    paras: list[str] = []

    def flush_bullets() -> None:
        nonlocal bullets, current_h
        if current_h and bullets:
            sections.append(("h", current_h))
            sections.append(("bullets", list(bullets)))
            bullets = []

    def flush_para() -> None:
        nonlocal paras, current_h
        if current_h and paras:
            sections.append(("h", current_h))
            sections.append(("p", "\n\n".join(paras)))
            paras = []

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("# ") and not s.startswith("##"):
            doc_title = s[2:].strip()
            continue
        if s.startswith("## "):
            flush_bullets()
            flush_para()
            current_h = s[3:].strip()
            continue
        if s.startswith("- "):
            if current_h and paras:
                flush_para()
            bullets.append(s[2:].strip())
            continue
        if current_h:
            if bullets:
                flush_bullets()
            paras.append(s)

    flush_bullets()
    flush_para()
    if current_h and not sections:
        sections.append(("h", current_h))
    return doc_title, sections


def _story_from_sections(
    doc_title: str,
    sections: list[tuple[str, str | list[str]]],
    body_font: str,
) -> list:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "T",
        parent=styles["Heading1"],
        fontName=body_font,
        fontSize=16,
        leading=20,
        alignment=TA_LEFT,
        spaceAfter=14,
    )
    h_style = ParagraphStyle(
        "H",
        parent=styles["Heading2"],
        fontName=body_font,
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "B",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=10,
        leading=13.5,
        alignment=TA_LEFT,
    )
    bullet_style = ParagraphStyle(
        "BL",
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-10,
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "M",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#333333"),
    )

    story: list = []
    story.append(
        Paragraph(
            "<b>MachineReadableMeta</b> "
            "document_type=GPTHub_architecture_submission; "
            "encoding=UTF-8; "
            "human_pages=1-3_figures; "
            "ai_appendix=mermaid_source_pages_follow",
            meta_style,
        )
    )
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(_xmlescape(doc_title), title_style))

    for kind, payload in sections:
        if kind == "h":
            story.append(Paragraph(_xmlescape(str(payload)), h_style))
        elif kind == "p":
            story.append(Paragraph(_xmlescape(str(payload)).replace("\n\n", "<br/><br/>"), body_style))
        elif kind == "bullets":
            assert isinstance(payload, list)
            for b in payload:
                story.append(Paragraph("• " + _xmlescape(b), bullet_style))
        story.append(Spacer(1, 0.12 * cm))

    story.append(PageBreak())
    return story


def _scaled_image(path: Path, max_width: float) -> RLImage:
    with PILImage.open(path) as im:
        w_px, h_px = im.size
    aspect = h_px / max(float(w_px), 1.0)
    w = max_width
    h = w * aspect
    max_h = 24 * cm
    if h > max_h:
        h = max_h
        w = h / aspect
    return RLImage(str(path), width=w, height=h)


def _mermaid_appendix_story(
    mmd_path: Path,
    appendix_title: str,
    mono_style: ParagraphStyle,
    head_style: ParagraphStyle,
) -> list:
    raw = mmd_path.read_text(encoding="utf-8").strip()
    lines = raw.splitlines()
    chunks: list[str] = []
    for i in range(0, len(lines), MERMAID_CHUNK_LINES):
        chunks.append("\n".join(lines[i : i + MERMAID_CHUNK_LINES]))
    out: list = []
    out.append(Paragraph(_xmlescape(appendix_title), head_style))
    out.append(Spacer(1, 0.2 * cm))
    for idx, chunk in enumerate(chunks):
        if idx:
            out.append(PageBreak())
        hdr = f"--- {mmd_path.name} part {idx + 1}/{len(chunks)} ---\n"
        out.append(Preformatted(hdr + chunk, mono_style, maxLineLength=MAX_LINE_LEN))
    return out


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission-dir", type=Path, default=SUB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    sub = args.submission_dir.resolve()
    out = args.out.resolve()

    txt_path = sub / "ARCHITECTURE_SUBMISSION_RU.txt"
    arch_png = sub / "architecture.png"
    flow_png = sub / "user_flow.png"
    arch_mmd = sub / "architecture.mmd"
    flow_mmd = sub / "user_flow.mmd"
    for p in (txt_path, arch_png, flow_png, arch_mmd, flow_mmd):
        if not p.is_file():
            raise SystemExit(f"missing required file: {p}")

    body_font, _bold_unused = _register_fonts()
    styles = getSampleStyleSheet()
    caption_style = ParagraphStyle(
        "Cap",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )
    mono_style = ParagraphStyle(
        "Mono",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=7.5,
        leading=9,
        alignment=TA_LEFT,
    )
    appendix_head_style = ParagraphStyle(
        "AppHead",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )

    doc_title, sections = _parse_submission_txt(txt_path.read_text(encoding="utf-8"))
    story = _story_from_sections(doc_title, sections, body_font)

    content_w = A4[0] - 3.6 * cm
    story.append(Paragraph(_xmlescape("Контур сервисов и моделей (PNG)"), caption_style))
    story.append(_scaled_image(arch_png, content_w))
    story.append(PageBreak())
    story.append(Paragraph(_xmlescape("User Flow — один чат (PNG)"), caption_style))
    story.append(_scaled_image(flow_png, content_w))
    story.append(PageBreak())

    story.extend(
        _mermaid_appendix_story(
            arch_mmd,
            "Приложение А — Исходник Mermaid: контур сервисов (architecture.mmd). "
            "Текст ниже извлекается из PDF без OCR.",
            mono_style,
            appendix_head_style,
        )
    )
    story.append(PageBreak())
    story.extend(
        _mermaid_appendix_story(
            flow_mmd,
            "Приложение Б — Исходник Mermaid: User Flow (user_flow.mmd). "
            "Текст ниже извлекается из PDF без OCR.",
            mono_style,
            appendix_head_style,
        )
    )

    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="GPTHub architecture submission",
        author="GPTHub Prod",
    )
    doc.build(story)
    logger.info("wrote %s (%s bytes)", out.relative_to(ROOT), out.stat().st_size)


if __name__ == "__main__":
    main()
