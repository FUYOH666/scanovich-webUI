#!/usr/bin/env python3
"""Build docs/submission/GPTHub_features_matrix.xlsx from FEATURE_MATRIX.md tables.

Run from repo root:
  uv run --with openpyxl python scripts/build_features_xlsx.py

Regenerate whenever [FEATURE_MATRIX.md](FEATURE_MATRIX.md) changes.
"""

from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "FEATURE_MATRIX.md"
OUT = ROOT / "docs" / "submission" / "GPTHub_features_matrix.xlsx"


def parse_matrix_tables(md: str) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    in_table = False
    for line in md.splitlines():
        if not line.startswith("|"):
            in_table = False
            continue
        if re.match(r"^\|\s*Row\s*\|", line):
            in_table = True
            continue
        if not in_table:
            continue
        if re.match(r"^\|\s*---", line):
            continue
        parts = [p.strip() for p in line.strip().split("|")]
        parts = [p for p in parts if p]
        if len(parts) >= 4 and parts[0].isdigit():
            rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def main() -> None:
    data = parse_matrix_tables(MATRIX.read_text(encoding="utf-8"))
    if len(data) != 15:
        raise SystemExit(f"expected 15 feature rows, got {len(data)} — check {MATRIX}")

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Features"
    headers = ("Row", "Feature", "Status", "How it works in this repo")
    ws.append(list(headers))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in data:
        ws.append(list(row))
    ws.freeze_panes = "A2"
    for col in ws.columns:
        maxlen = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(maxlen + 2, 12), 90)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
