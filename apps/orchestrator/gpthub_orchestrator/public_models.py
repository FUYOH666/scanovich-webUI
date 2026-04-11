"""Public model catalog for Open WebUI (single facade vs full LiteLLM list)."""

from __future__ import annotations

import copy
import logging
from typing import Any

from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)


def apply_models_catalog(litellm_payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """
    If catalog is ``all``, return a deep copy of the LiteLLM JSON.
    If ``single_public``, return OpenAI-style list with one model id (facade).
    """
    if settings.orchestrator_models_catalog == "all":
        return copy.deepcopy(litellm_payload)

    public_id = settings.orchestrator_public_model_id
    data = litellm_payload.get("data")
    template: dict[str, Any] = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                template = {k: v for k, v in item.items() if k != "id"}
                break

    entry: dict[str, Any] = {"object": "model", "id": public_id}
    entry.update({k: v for k, v in template.items() if k != "object"})
    entry["object"] = "model"
    entry["id"] = public_id

    out = {"object": "list", "data": [entry]}
    if isinstance(litellm_payload.get("object"), str) and litellm_payload["object"] != "list":
        out["object"] = litellm_payload["object"]
    return out


def map_facade_model_to_litellm(body: dict[str, Any], settings: Settings) -> None:
    """
    When the client sends the public facade id and auto-routing is off, LiteLLM has no such
    model — map to ``default_text_model``. When auto-routing is on, ``main`` overwrites model
    from the router chain; no change needed here.
    """
    if settings.auto_route_model:
        return
    mid = body.get("model")
    if not isinstance(mid, str):
        return
    if mid.strip() != settings.orchestrator_public_model_id:
        return
    body["model"] = settings.default_text_model
    logger.info(
        "facade_model_mapped facade=%s litellm_alias=%s",
        settings.orchestrator_public_model_id,
        settings.default_text_model,
    )
