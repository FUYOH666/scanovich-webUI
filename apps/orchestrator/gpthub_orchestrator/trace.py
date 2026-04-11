"""Execution trace serialization for logs and optional response headers."""

from __future__ import annotations

import base64
import json
from typing import Any


def compute_fallback_used(orchestrator_fallback: dict[str, Any] | None) -> bool:
    """True if orchestrator tried more than one model alias (non-stream path)."""
    if not orchestrator_fallback:
        return False
    if orchestrator_fallback.get("mode") == "stream_single_attempt":
        return False
    if int(orchestrator_fallback.get("retries_after_failure") or 0) > 0:
        return True
    attempts = orchestrator_fallback.get("attempts") or []
    return len(attempts) > 1


def _attachments_detected(classification: dict[str, Any]) -> list[str]:
    modalities = classification.get("modalities")
    if isinstance(modalities, list):
        return [str(m) for m in modalities if m]
    return []


def build_trace(
    *,
    classification: dict[str, Any],
    router_suggestion: dict[str, Any],
    model_used: str,
    artifacts: list[dict[str, Any]] | None = None,
    orchestrator_fallback: dict[str, Any] | None = None,
    prompt_version: str | None = None,
    classifier_source: str = "heuristic",
    server_clock_iso: str | None = None,
    canned_response: bool | None = None,
    ingest_ms: float | None = None,
) -> dict[str, Any]:
    rs = router_suggestion or {}
    tt = classification.get("task_type")
    fb_used = compute_fallback_used(orchestrator_fallback)
    trace: dict[str, Any] = {
        "detected_task": tt,
        "task_type": tt,
        "modalities": classification.get("modalities"),
        "complexity_score": classification.get("complexity_score"),
        "router_suggestion": router_suggestion,
        "model_role": rs.get("model_role"),
        "fallback_aliases": rs.get("fallback_aliases"),
        "model_used": model_used,
        "selected_model": model_used,
        "fallback_used": fb_used,
        "artifacts": artifacts or [],
        "tools_used": [],
        "classifier_source": classifier_source,
        "attachments_detected": _attachments_detected(classification),
    }
    if prompt_version is not None:
        trace["prompt_version"] = prompt_version
    if server_clock_iso is not None:
        trace["server_clock_iso"] = server_clock_iso
    if canned_response is True:
        trace["canned_response"] = True
    if orchestrator_fallback is not None:
        trace["orchestrator_fallback"] = orchestrator_fallback
    if ingest_ms is not None:
        trace["ingest_ms"] = round(float(ingest_ms), 3)
    return trace


def trace_to_header_value(trace: dict[str, Any]) -> str:
    raw = json.dumps(trace, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")
