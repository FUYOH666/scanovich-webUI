"""Merge GPTHub role system prompts with client messages (Open WebUI / API)."""

from __future__ import annotations

from typing import Any

from gpthub_orchestrator.role_prompts import RolePromptsFile, prompt_for_role


def _system_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
        return " ".join(parts).strip()
    return ""


def _split_system_and_rest(
    messages: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    client_system: list[str] = []
    rest: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "system":
            t = _system_message_text(m.get("content"))
            if t:
                client_system.append(t)
        else:
            rest.append(m)
    return client_system, rest


def merge_role_and_client_system(role_text: str, client_parts: list[str]) -> str:
    if not client_parts:
        return role_text
    suffix = "\n\n--- Additional instructions (from chat client) ---\n" + "\n\n".join(client_parts)
    return role_text + suffix


def apply_role_system_messages(
    messages: list[dict[str, Any]],
    role_key: str,
    prompts: RolePromptsFile,
    *,
    session_clock_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """
    Prepend a single system message: optional session clock, GPTHub role prompt, client system blocks.

    See docs/PROMPT_PRECEDENCE.md for ordering rules.
    """
    role_text = prompt_for_role(prompts, role_key)
    client_system, rest = _split_system_and_rest(messages)
    merged = merge_role_and_client_system(role_text, client_system)
    if session_clock_prefix:
        merged = session_clock_prefix + "\n\n" + merged
    return [{"role": "system", "content": merged}, *rest]
