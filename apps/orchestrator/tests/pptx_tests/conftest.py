"""Fixtures and env defaults for PPTX package tests."""

from __future__ import annotations

import os

import pytest

from gpthub_orchestrator.model_registry import load_model_roles
from gpthub_orchestrator.settings import Settings

os.environ.setdefault("LITELLM_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("ORCHESTRATOR_API_KEY", "k")


@pytest.fixture(autouse=True)
def _clear_model_roles_cache() -> None:
    load_model_roles.cache_clear()
    yield
    load_model_roles.cache_clear()


@pytest.fixture
def pptx_settings() -> Settings:
    return Settings(
        litellm_base_url="http://litellm.test",
        orchestrator_api_key="k",
        pptx_asset_templates_enabled=False,
        # Tests use tiny JSON payloads; prod default 250 would reject them.
        pptx_slide_min_visible_chars=0,
    )
