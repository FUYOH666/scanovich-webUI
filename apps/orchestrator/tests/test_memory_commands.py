"""Parser for memory commands: remember / forget / recall."""

from __future__ import annotations

import pytest

from gpthub_orchestrator.memory.commands import parse_memory_command


@pytest.mark.parametrize(
    "text,expected_payload",
    [
        ("Запомни, что я люблю Go", "я люблю Go"),
        ("запомни: я пью эспрессо по утрам", "я пью эспрессо по утрам"),
        ("Запомни я работаю в МТС", "я работаю в МТС"),
        ("remember that I love rust", "I love rust"),
        ("Remember: my cat is Murzik", "my cat is Murzik"),
        ("/remember I prefer dark theme", "I prefer dark theme"),
    ],
)
def test_remember_parses_payload(text: str, expected_payload: str):
    cmd = parse_memory_command(text)
    assert cmd is not None
    assert cmd.kind == "remember"
    assert cmd.payload == expected_payload


@pytest.mark.parametrize(
    "text,expected_payload",
    [
        ("Забудь про эспрессо", "эспрессо"),
        ("забудь о моей старой работе", "моей старой работе"),
        ("forget about my cat", "my cat"),
        ("/forget dark theme", "dark theme"),
    ],
)
def test_forget_parses_payload(text: str, expected_payload: str):
    cmd = parse_memory_command(text)
    assert cmd is not None
    assert cmd.kind == "forget"
    assert cmd.payload == expected_payload


@pytest.mark.parametrize(
    "text",
    [
        "Забудь всё",
        "забудь все обо мне",
        "forget everything",
        "forget all about me",
        "/forget_all",
    ],
)
def test_forget_all(text: str):
    cmd = parse_memory_command(text)
    assert cmd is not None
    assert cmd.kind == "forget_all"


@pytest.mark.parametrize(
    "text",
    [
        "Что ты обо мне помнишь?",
        "что ты помнишь",
        "что ты знаешь обо мне?",
        "what do you remember about me?",
        "what do you know about me",
        "/memories",
        "/memory",
    ],
)
def test_recall_all(text: str):
    cmd = parse_memory_command(text)
    assert cmd is not None
    assert cmd.kind == "recall_all"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Привет!",
        "Расскажи анекдот",
        "what is the capital of France",
        "Напиши код на Python",
    ],
)
def test_non_commands_return_none(text: str):
    assert parse_memory_command(text) is None
