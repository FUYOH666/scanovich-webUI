"""LiteLLM vendored config contains optional PPTX benchmark aliases."""

from __future__ import annotations

from pathlib import Path


def test_litellm_config_has_pptx_benchmark_aliases() -> None:
    repo = Path(__file__).resolve().parents[3]
    cfg = repo / "infra" / "litellm" / "config.yaml"
    text = cfg.read_text(encoding="utf-8")
    assert "gpt-hub-pptx-llama33" in text
    assert "gpt-hub-pptx-qwen235a22" in text
    assert "llama-3.3-70b-instruct" in text
    assert "Qwen3-235B-A22B-Instruct-2507-FP8" in text
