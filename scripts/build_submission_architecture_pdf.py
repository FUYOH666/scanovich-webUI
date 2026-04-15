#!/usr/bin/env python3
"""Build a single PDF for hackathon upload: prose + architecture + user flow."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
from PIL import Image


def _pick_cyrillic_font() -> str | None:
    """Return path to a TTF that supports Cyrillic (macOS / Linux common paths)."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).is_file():
            return p
    for f in font_manager.fontManager.ttflist:
        name = (f.name or "").lower()
        if "arial unicode" in name or "noto sans" in name or "dejavu sans" in name:
            return str(f.fname)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--submission-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs" / "submission",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PDF path (default: submission-dir/GPTHub_architecture_submission.pdf)",
    )
    args = parser.parse_args()
    sub = args.submission_dir.resolve()
    out = args.out or (sub / "GPTHub_architecture_submission.pdf")
    txt_path = sub / "ARCHITECTURE_SUBMISSION_RU.txt"
    arch_png = sub / "architecture.png"
    flow_png = sub / "user_flow.png"
    for p in (txt_path, arch_png, flow_png):
        if not p.is_file():
            raise SystemExit(f"missing required file: {p}")

    raw = txt_path.read_text(encoding="utf-8")
    # Wrap for A4 text column (~95 chars at fontsize 9)
    paras = [textwrap.fill(p.strip(), width=95) for p in raw.split("\n\n") if p.strip()]
    body = "\n\n".join(paras)
    font_path = _pick_cyrillic_font()
    if font_path:
        font_manager.fontManager.addfont(font_path)
        prop = font_manager.FontProperties(fname=font_path)
        plt.rcParams["font.family"] = prop.get_name()
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"

    # A4 portrait in inches
    figsize = (8.27, 11.69)

    with PdfPages(out) as pdf:
        # Page 1 — text
        fig, ax = plt.subplots(figsize=figsize)
        ax.axis("off")
        ax.set_title("GPTHub Prod — архитектура и User Flow", fontsize=14, pad=12)
        ax.text(
            0.05,
            0.92,
            body,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            linespacing=1.35,
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        for label, img_path in (
            ("Контур сервисов и моделей", arch_png),
            ("User Flow — один чат", flow_png),
        ):
            fig, ax = plt.subplots(figsize=figsize)
            ax.axis("off")
            ax.set_title(label, fontsize=12, pad=8)
            ax.imshow(Image.open(img_path))
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    print(f"Wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
