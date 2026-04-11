"""Load role-keyed system prompts from packaged YAML."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from gpthub_orchestrator.model_registry import MODEL_ROLE_KEYS

logger = logging.getLogger(__name__)

_PACKAGE_DATA = Path(__file__).resolve().parent / "data" / "role_prompts.yaml"


class RolePromptsFile(BaseModel):
    version: int = 1
    prompt_version: str = Field(..., min_length=1)
    prompts: dict[str, str]

    @field_validator("prompts")
    @classmethod
    def non_empty_strings(cls, v: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, text in v.items():
            s = str(text).strip()
            if not s:
                raise ValueError(f"prompt for role {k!r} must be non-empty")
            out[k] = text
        return out

    @model_validator(mode="after")
    def all_roles_present(self) -> RolePromptsFile:
        missing = MODEL_ROLE_KEYS - set(self.prompts.keys())
        if missing:
            raise ValueError(f"role_prompts.yaml missing prompts for roles: {sorted(missing)}")
        return self


@lru_cache(maxsize=4)
def load_role_prompts(path: str | None = None) -> RolePromptsFile:
    """Load prompts from ``path`` or default packaged ``role_prompts.yaml``."""
    p = Path(path) if path else _PACKAGE_DATA
    if not p.is_file():
        raise FileNotFoundError(f"role prompts file not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("role_prompts.yaml must parse to a mapping")
    parsed = RolePromptsFile.model_validate(raw)
    logger.info(
        "role_prompts_loaded path=%s version=%s prompt_version=%s",
        p,
        parsed.version,
        parsed.prompt_version,
    )
    return parsed


def prompt_for_role(data: RolePromptsFile, role_key: str) -> str:
    text = data.prompts.get(role_key)
    if text is None:
        raise KeyError(f"unknown model role for prompts: {role_key}")
    return text
