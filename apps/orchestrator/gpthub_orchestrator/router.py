"""Capability-based model routing: roles → LiteLLM alias chains (registry YAML)."""

from __future__ import annotations

import logging
from typing import Any

from gpthub_orchestrator.model_registry import (
    ROLE_DOC,
    ROLE_FAST_TEXT,
    ROLE_FAST_TEXT_CHAT,
    ROLE_REASONING_LOCAL,
    ROLE_REASONING_OPENROUTER,
    ROLE_VISION,
    aliases_for_role,
    load_model_roles,
)
from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)


def choose_model(classification: dict[str, Any], settings: Settings) -> dict[str, Any]:
    modalities = classification.get("modalities") or ["text"]
    task_type = classification.get("task_type") or "simple_chat"
    has_image = "image" in modalities

    registry = load_model_roles(settings.model_roles_path)

    if has_image:
        role_key = ROLE_VISION
        reason = "vision_multimodal_content"
    elif task_type in ("summarization", "file_analysis"):
        role_key = ROLE_DOC
        reason = "document_or_summary_heuristic"
    elif task_type in ("code_help", "multimodal_workflow"):
        if settings.code_route_preference == "openrouter":
            role_key = ROLE_REASONING_OPENROUTER
            reason = "code_or_deep_analysis_openrouter"
        else:
            role_key = ROLE_REASONING_LOCAL
            reason = "code_or_deep_analysis_local_first"
    elif task_type == "greeting_or_tiny":
        role_key = ROLE_FAST_TEXT_CHAT
        reason = "greeting_or_tiny_chat"
    else:
        role_key = ROLE_FAST_TEXT
        reason = "default_text_chat"

    chain = aliases_for_role(registry, role_key)
    meta = {
        "model_name": chain[0],
        "model_role": role_key,
        "fallback_aliases": chain,
        "reason": reason,
        "task_type": task_type,
    }
    logger.info("model_router_choice %s", meta)
    return meta
