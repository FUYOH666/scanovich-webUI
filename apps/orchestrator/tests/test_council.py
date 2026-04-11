"""Expert Council (WOW-1): intent, fan-out, synthesis, fallback, trace."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from gpthub_orchestrator.council import (
    CouncilError,
    CouncilResult,
    ExpertOpinion,
    ExpertSpec,
    _build_synthesis_messages,  # type: ignore[reportPrivateUsage]
    build_council_chat_completion,
    build_council_sse_chunks,
    default_experts,
    extract_council_question,
    is_council_request,
    run_council,
)
from gpthub_orchestrator.settings import Settings


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _mk_settings(**over: Any) -> Settings:
    base: dict[str, Any] = {
        "litellm_base_url": "http://litellm:4000",
        "orchestrator_api_key": "t",
        "mws_gpt_api_base": "https://api.gpt.mws.ru/v1",
        "mws_gpt_api_key": "sk-test",
        # Keep timeouts short so tests never hang.
        "council_branch_timeout_seconds": 10.0,
        "council_synthesis_timeout_seconds": 10.0,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _chat_response(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 0,
        "model": "mock",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _make_router(
    *,
    settings: Settings | None = None,
    strong_content: str = "strong-answer",
    reasoning_content: str = "reasoning-answer",
    doc_content: str = "doc-answer",
    synthesis_content: str = "SYNTHESIZED_FINAL",
    fail_models: set[str] | None = None,
    synthesis_status: int = 200,
) -> tuple[httpx.MockTransport, list[dict[str, Any]]]:
    """Build a MockTransport that routes by model name + system prompt cues."""
    s = settings or _mk_settings()
    fail_models = fail_models or set()
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/chat/completions")
        body = json.loads(request.read())
        model = body.get("model", "")
        calls.append({"model": model, "messages": body.get("messages", [])})
        if model in fail_models:
            return httpx.Response(502, json={"error": {"message": "boom"}})
        sys_msg = (
            body.get("messages", [{}])[0].get("content", "")
            if body.get("messages")
            else ""
        )
        is_synthesis = "синтезатор" in sys_msg.lower()
        is_fallback_single = "fallback-режим" in sys_msg
        if is_synthesis or is_fallback_single:
            if synthesis_status >= 400:
                return httpx.Response(synthesis_status, json={"error": {"message": "nope"}})
            return httpx.Response(200, json=_chat_response(synthesis_content))
        # Route expert calls by matching the spec model, not by substring,
        # so the test survives default-model churn in settings.
        if model == s.council_expert_strong:
            return httpx.Response(200, json=_chat_response(strong_content))
        if model == s.council_expert_reasoning:
            return httpx.Response(200, json=_chat_response(reasoning_content))
        if model == s.council_expert_doc:
            return httpx.Response(200, json=_chat_response(doc_content))
        return httpx.Response(200, json=_chat_response("generic"))

    return httpx.MockTransport(handler), calls


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "/research RAG architectures in enterprise",
        "Проведи глубокое исследование по safety agents",
        "сделай глубокий анализ transformer scaling",
        "Do a deep research on MLOps frameworks",
        "expert council on monorepo strategy",
        "мультиэкспертный обзор подходов к векторному поиску",
    ],
)
def test_council_intent_positive(text: str) -> None:
    assert is_council_request(text)


@pytest.mark.parametrize(
    "text",
    [
        "Объясни, как работает RAG в двух предложениях",
        "Напиши функцию поиска простых чисел на python",
        "Нарисуй рыжего кота в шляпе",
        "Привет!",
        "",
        "x" * 9000,  # huge paste — don't hijack
    ],
)
def test_council_intent_negative(text: str) -> None:
    assert not is_council_request(text)


def test_extract_council_question_strips_slash() -> None:
    assert (
        extract_council_question("/research RAG retrieval strategies")
        == "RAG retrieval strategies"
    )


def test_extract_council_question_passthrough() -> None:
    q = "Проведи глубокое исследование по safety agents"
    assert extract_council_question(q) == q


# ---------------------------------------------------------------------------
# default_experts wiring
# ---------------------------------------------------------------------------


def test_default_experts_three_distinct_models() -> None:
    s = _mk_settings()
    experts = default_experts(s)
    assert len(experts) == 3
    models = {e.model for e in experts}
    assert len(models) == 3
    keys = {e.key for e in experts}
    assert keys == {"strong", "reasoning", "doc"}


# ---------------------------------------------------------------------------
# Full happy path — all 3 experts succeed + synthesis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_council_happy_path_synthesizes() -> None:
    s = _mk_settings()
    transport, calls = _make_router(
        settings=s,
        strong_content="Generalist view on RAG.",
        reasoning_content="Reasoning trade-offs list.",
        doc_content="Doc fact-baseline.",
        synthesis_content="FINAL_SYNTHESIS_TEXT",
    )
    async with httpx.AsyncClient(transport=transport) as http:
        result = await run_council(
            http,
            settings=s,
            base_url="http://litellm:4000",
            auth_header="Bearer master",
            question="RAG for enterprise",
        )
    assert isinstance(result, CouncilResult)
    assert result.final_text == "FINAL_SYNTHESIS_TEXT"
    assert result.fallback_used is False
    assert len(result.opinions) == 3
    assert {o.key for o in result.opinions} == {"strong", "reasoning", "doc"}
    assert not result.failures
    # 3 expert calls + 1 synthesis
    assert len(calls) == 4
    # Each expert was called with its persona system prompt
    personas = {c["messages"][0]["content"][:10] for c in calls[:3]}
    assert all(p.startswith("Ты — ") for p in personas)


# ---------------------------------------------------------------------------
# Partial failure — one expert down, still synthesizes with 2 opinions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_council_two_of_three_still_synthesizes() -> None:
    s = _mk_settings()
    transport, calls = _make_router(
        settings=s,
        fail_models={s.council_expert_doc},
        synthesis_content="SYNTH_WITH_2",
    )
    async with httpx.AsyncClient(transport=transport) as http:
        result = await run_council(
            http,
            settings=s,
            base_url="http://litellm:4000",
            auth_header="Bearer master",
            question="question",
        )
    assert result.final_text == "SYNTH_WITH_2"
    assert result.fallback_used is False
    assert len(result.opinions) == 2
    assert len(result.failures) == 1
    assert result.failures[0].key == "doc"
    payload = result.trace_payload()
    assert payload["short_circuit"] == "expert_council"
    assert len(payload["branches_ok"]) == 2
    assert len(payload["branches_failed"]) == 1


# ---------------------------------------------------------------------------
# Fallback: fewer than min branches → strong-only reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_council_fallback_when_only_one_branch_ok() -> None:
    s = _mk_settings()
    transport, _calls = _make_router(
        settings=s,
        fail_models={s.council_expert_reasoning, s.council_expert_doc},
        synthesis_content="STRONG_ONLY_FALLBACK",
    )
    async with httpx.AsyncClient(transport=transport) as http:
        result = await run_council(
            http,
            settings=s,
            base_url="http://litellm:4000",
            auth_header="Bearer master",
            question="q",
        )
    assert result.fallback_used is True
    assert result.final_text == "STRONG_ONLY_FALLBACK"
    assert len(result.opinions) == 1
    assert len(result.failures) == 2


@pytest.mark.asyncio
async def test_run_council_fallback_when_all_fail() -> None:
    s = _mk_settings()
    transport, _calls = _make_router(
        settings=s,
        fail_models={
            s.council_expert_strong,
            s.council_expert_reasoning,
            s.council_expert_doc,
            s.council_synthesis_model,
        },
    )
    async with httpx.AsyncClient(transport=transport) as http:
        result = await run_council(
            http,
            settings=s,
            base_url="http://litellm:4000",
            auth_header="Bearer master",
            question="q",
        )
    assert result.fallback_used is True
    assert "ошибк" in result.final_text.lower()
    assert not result.opinions
    assert len(result.failures) == 3


# ---------------------------------------------------------------------------
# Synthesis failure → emergency composite response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_council_emergency_composite_when_synthesis_fails() -> None:
    s = _mk_settings()
    transport, _calls = _make_router(
        settings=s,
        strong_content="STRONG_BODY",
        reasoning_content="REASON_BODY",
        doc_content="DOC_BODY",
        synthesis_status=500,
    )
    async with httpx.AsyncClient(transport=transport) as http:
        result = await run_council(
            http,
            settings=s,
            base_url="http://litellm:4000",
            auth_header="Bearer master",
            question="q",
        )
    assert result.fallback_used is True
    assert "STRONG_BODY" in result.final_text
    assert "REASON_BODY" in result.final_text
    assert "DOC_BODY" in result.final_text
    assert len(result.opinions) == 3


# ---------------------------------------------------------------------------
# Synthesis message builder
# ---------------------------------------------------------------------------


def test_build_synthesis_messages_includes_all_opinions() -> None:
    opinions = [
        ExpertOpinion(
            key="strong",
            model="gpt-hub-strong",
            label="Generalist",
            content="STRONG_TEXT",
            latency_ms=100,
        ),
        ExpertOpinion(
            key="reasoning",
            model="gpt-hub-reasoning-or",
            label="Reasoning",
            content="REASON_TEXT",
            latency_ms=200,
        ),
    ]
    msgs = _build_synthesis_messages("What is RAG?", opinions)
    assert len(msgs) == 2
    assert "синтезатор" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "What is RAG?" in user
    assert "STRONG_TEXT" in user
    assert "REASON_TEXT" in user
    assert "Generalist" in user
    assert "Reasoning" in user


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def test_build_council_chat_completion_shape() -> None:
    out = build_council_chat_completion(model_label="gpt-hub", text="hello")
    assert out["object"] == "chat.completion"
    assert out["choices"][0]["message"]["content"] == "hello"
    assert out["model"] == "gpt-hub"
    assert out["id"].startswith("chatcmpl-council-")


def test_build_council_sse_chunks_ends_with_done() -> None:
    chunks = build_council_sse_chunks("gpt-hub", "hello")
    assert chunks[-1] == b"data: [DONE]\n\n"
    first = json.loads(chunks[0].decode("utf-8").removeprefix("data: ").strip())
    assert first["choices"][0]["delta"]["content"] == "hello"


# ---------------------------------------------------------------------------
# run_council contract: empty question rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_council_rejects_empty_question() -> None:
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError):
            await run_council(
                http,
                settings=_mk_settings(),
                base_url="http://litellm:4000",
                auth_header="Bearer master",
                question="   ",
            )


# ---------------------------------------------------------------------------
# Classifier wiring: DEEP_RESEARCH gets set on council-intent messages
# ---------------------------------------------------------------------------


def test_classifier_detects_deep_research() -> None:
    from gpthub_orchestrator.classifier import classify_messages

    result = classify_messages(
        [
            {
                "role": "user",
                "content": "/research Что такое retrieval-augmented generation?",
            }
        ]
    )
    assert result["task_type"] == "deep_research"


def test_classifier_ignores_research_when_image_present() -> None:
    from gpthub_orchestrator.classifier import classify_messages

    result = classify_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "/research this diagram"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
                ],
            }
        ]
    )
    # Image wins — council short-circuit should not hijack vision flows.
    assert result["task_type"] in ("image_analysis", "multimodal_workflow")


def test_call_experts_with_raising_expert_spec_unused() -> None:
    """Sanity check that ExpertSpec is a dataclass we can build by hand."""
    spec = ExpertSpec(key="x", model="gpt-hub-strong", persona="p", label="L")
    assert spec.key == "x"
    assert spec.model == "gpt-hub-strong"


@pytest.mark.asyncio
async def test_run_council_strips_think_blocks_from_experts() -> None:
    """Expert CoT leakage must not reach synthesis or emergency composite."""
    s = _mk_settings()
    transport, _calls = _make_router(
        settings=s,
        strong_content="<think>internal reasoning</think>Clean generalist take.",
        reasoning_content="Plain reasoning text.",
        doc_content="<think>stuff</think>Clean doc take.",
        synthesis_status=500,  # force emergency composite so we see expert content verbatim
    )
    async with httpx.AsyncClient(transport=transport) as http:
        result = await run_council(
            http,
            settings=s,
            base_url="http://litellm:4000",
            auth_header="Bearer master",
            question="q",
        )
    # Emergency composite path (synthesis failed).
    assert result.fallback_used is True
    assert "internal reasoning" not in result.final_text
    assert "<think>" not in result.final_text
    assert "Clean generalist take." in result.final_text
    assert "Clean doc take." in result.final_text
    # Opinions themselves were cleaned, not just the final text.
    assert all("<think>" not in op.content for op in result.opinions)


def test_strip_cot_blocks_handles_unclosed_think() -> None:
    from gpthub_orchestrator.council import _strip_cot_blocks  # type: ignore[reportPrivateUsage]

    assert _strip_cot_blocks("Answer. <think>truncated") == "Answer."
    assert _strip_cot_blocks("<think>only thoughts</think>Final.") == "Final."
    assert _strip_cot_blocks("No think tags here") == "No think tags here"
    # Whole answer wrapped in an unclosed <think>: we must NOT return empty.
    result = _strip_cot_blocks("<think>entire body with no closing tag")
    assert result != ""
    assert "entire body" in result
