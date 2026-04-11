import pytest

from gpthub_orchestrator.model_registry import ModelRolesFile, RoleAliases, aliases_for_role, load_model_roles


def test_load_default_registry():
    load_model_roles.cache_clear()
    reg = load_model_roles()
    assert "fast_text" in reg.roles
    assert reg.roles["fast_text"].aliases[0] == "gpt-hub-turbo"


def test_aliases_for_role_unknown():
    load_model_roles.cache_clear()
    reg = load_model_roles()
    with pytest.raises(KeyError):
        aliases_for_role(reg, "nonexistent_role")


def test_role_aliases_validation_empty():
    with pytest.raises(Exception):
        RoleAliases(aliases=[])


def test_model_roles_file_schema():
    raw = {
        "version": 1,
        "roles": {
            "fast_text_chat": {"aliases": ["f"]},
            "fast_text": {"aliases": ["a", "b"]},
            "doc_synthesis": {"aliases": ["d"]},
            "reasoning_code_local": {"aliases": ["t"]},
            "reasoning_code_openrouter": {"aliases": ["r"]},
            "vision_general": {"aliases": ["v"]},
        },
    }
    m = ModelRolesFile.model_validate(raw)
    assert m.roles["fast_text"].aliases == ["a", "b"]
