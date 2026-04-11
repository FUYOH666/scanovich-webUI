"""Classifier greeting_or_tiny heuristic."""

from __future__ import annotations

import pytest

from gpthub_orchestrator.classifier import classify_messages


@pytest.mark.parametrize(
    ("content", "expected_task"),
    [
        ("привет", "greeting_or_tiny"),
        ("как дела?", "greeting_or_tiny"),
        ("Как ты?", "greeting_or_tiny"),
        ("Привет, как дела?", "greeting_or_tiny"),
        ("Hello there!", "greeting_or_tiny"),
        ("спасибо", "greeting_or_tiny"),
        ("OK", "greeting_or_tiny"),
        (
            "Объясни в двух предложениях, что такое список в Python.",
            "simple_chat",
        ),
        ("Привет, какой сегодня день?", "simple_chat"),
        ("Hi, what day is it?", "simple_chat"),
        ("привет, что такое список в Python?", "simple_chat"),
        ("Traceback: NameError", "code_help"),
    ],
)
def test_task_type_greeting_vs_chat(content: str, expected_task: str):
    cl = classify_messages([{"role": "user", "content": content}])
    assert cl["task_type"] == expected_task
