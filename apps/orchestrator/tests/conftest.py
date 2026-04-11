import pytest

from gpthub_orchestrator.model_registry import load_model_roles
from gpthub_orchestrator.role_prompts import load_role_prompts


@pytest.fixture(autouse=True)
def clear_orchestrator_yaml_caches():
    load_model_roles.cache_clear()
    load_role_prompts.cache_clear()
    yield
    load_model_roles.cache_clear()
    load_role_prompts.cache_clear()
