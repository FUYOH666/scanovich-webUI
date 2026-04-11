import os

import pytest

os.environ.setdefault("LITELLM_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("ORCHESTRATOR_API_KEY", "k")

from gpthub_orchestrator.model_registry import load_model_roles
from gpthub_orchestrator.router import choose_model
from gpthub_orchestrator.settings import Settings


@pytest.fixture(autouse=True)
def clear_registry_cache():
    load_model_roles.cache_clear()
    yield
    load_model_roles.cache_clear()


def _settings(**kwargs):
    base = {
        "litellm_base_url": "http://127.0.0.1:9",
        "orchestrator_api_key": "k",
    }
    base.update(kwargs)
    return Settings(**base)


def test_router_vision_role():
    s = _settings()
    out = choose_model({"modalities": ["text", "image"], "task_type": "image_analysis"}, s)
    assert out["model_role"] == "vision_general"
    assert out["model_name"] == "gpt-hub-vision"
    assert "gpt-hub-fallback" in out["fallback_aliases"]


def test_router_doc_role():
    s = _settings()
    out = choose_model({"modalities": ["text"], "task_type": "summarization"}, s)
    assert out["model_role"] == "doc_synthesis"
    assert out["model_name"] == "gpt-hub-turbo"


def test_router_code_local_preference():
    s = _settings(code_route_preference="local")
    out = choose_model({"modalities": ["text"], "task_type": "code_help"}, s)
    assert out["model_role"] == "reasoning_code_local"
    assert out["model_name"] == "gpt-hub-turbo"


def test_router_code_openrouter_preference():
    s = _settings(code_route_preference="openrouter")
    out = choose_model({"modalities": ["text"], "task_type": "code_help"}, s)
    assert out["model_role"] == "reasoning_code_openrouter"
    assert out["model_name"] == "gpt-hub-turbo"


def test_router_fast_text():
    s = _settings()
    out = choose_model({"modalities": ["text"], "task_type": "simple_chat"}, s)
    assert out["model_role"] == "fast_text"
    assert out["model_name"] == "gpt-hub-turbo"


def test_router_greeting_or_tiny():
    s = _settings()
    out = choose_model({"modalities": ["text"], "task_type": "greeting_or_tiny"}, s)
    assert out["model_role"] == "fast_text_chat"
    assert out["model_name"] == "gpt-hub-turbo"
    assert "gpt-hub-strong" not in out["fallback_aliases"]
