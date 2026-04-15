"""Happy-path: defence deck script produces 10-slide pptx."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pptx import Presentation

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "build_defence_deck_pptx.py"
OUT = REPO_ROOT / "docs" / "submission" / "GPTHub_defence_10slides.pptx"
MD = REPO_ROOT / "docs" / "submission" / "SLIDES_10_RU.md"


@pytest.mark.skipif(not SCRIPT.is_file(), reason="build script missing")
def test_build_defence_deck_pptx_smoke() -> None:
    assert MD.is_file(), "SLIDES_10_RU.md required"
    r = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr or r.stdout
    assert OUT.is_file(), "pptx output missing"
    prs = Presentation(str(OUT))
    assert len(prs.slides) == 10
