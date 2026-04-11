"""Memory service: high-level orchestration used by `main.py`.

Responsibilities:
  1. Extract the last user text from an OpenAI-compatible messages list.
  2. If it matches a memory command → execute against `MemoryStore` and
     return a short-circuit chat.completion payload (the orchestrator never
     calls LiteLLM in this path — memory commands are fully local).
  3. Otherwise, if memory retrieval is enabled → embed the last user text,
     fetch top-K relevant facts, and build a system block the caller can
     inject just like an ingest artifact.

All external I/O (sqlite writes, embedding HTTP calls) is pushed into
`asyncio.to_thread` or awaited on httpx so the FastAPI request loop stays
non-blocking.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from gpthub_orchestrator.memory.commands import MemoryCommand, parse_memory_command
from gpthub_orchestrator.memory.embeddings import EmbeddingError, embed_one
from gpthub_orchestrator.memory.store import MemoryFact, MemoryStore
from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                str(p.get("text", ""))
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return " ".join(parts).strip()
    return ""


def resolve_user_id(messages: list[dict[str, Any]], default: str = "default") -> str:
    """Pick a stable user id from the request.

    Open WebUI does not forward an authenticated user id, so for a single-tenant
    demo we treat everyone as `default`. We still honour an explicit `user`
    field if present (OpenAI-compatible).
    """
    for m in messages:
        if m.get("role") == "user":
            uid = m.get("name") or m.get("user")
            if isinstance(uid, str) and uid.strip():
                return uid.strip()
    return default


# ---------------------------------------------------------------------------
# Short-circuit responses
# ---------------------------------------------------------------------------


def _chat_completion(model_label: str, content: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-mem-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def build_memory_sse_chunks(model_label: str, content: str) -> list[bytes]:
    import json as _json

    cid = f"chatcmpl-mem-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    first = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [
            {"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}
        ],
    }
    final = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return [
        b"data: " + _json.dumps(first, ensure_ascii=False).encode("utf-8") + b"\n\n",
        b"data: " + _json.dumps(final, ensure_ascii=False).encode("utf-8") + b"\n\n",
        b"data: [DONE]\n\n",
    ]


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------


@dataclass
class MemoryCommandResult:
    kind: str
    reply_text: str
    fact_count: int


async def execute_memory_command(
    cmd: MemoryCommand,
    *,
    store: MemoryStore,
    user_id: str,
    http: httpx.AsyncClient,
    settings: Settings,
) -> MemoryCommandResult:
    if cmd.kind == "remember":
        vec: list[float] | None = None
        try:
            vec = await embed_one(http, settings=settings, text=cmd.payload)
        except EmbeddingError as e:
            logger.warning("memory_remember_embed_failed err=%s", e)
        fact = await asyncio.to_thread(
            store.add_fact,
            user_id=user_id,
            content=cmd.payload,
            embedding=vec,
        )
        return MemoryCommandResult(
            kind="remember",
            reply_text=f"Запомнил: «{fact.content}».",
            fact_count=1,
        )

    if cmd.kind == "forget":
        n = await asyncio.to_thread(
            store.delete_by_substring,
            user_id=user_id,
            needle=cmd.payload,
        )
        if n == 0:
            return MemoryCommandResult(
                kind="forget",
                reply_text=f"У меня не было записей про «{cmd.payload}».",
                fact_count=0,
            )
        return MemoryCommandResult(
            kind="forget",
            reply_text=f"Удалил {n} запис{'ь' if n == 1 else 'и/ей'} про «{cmd.payload}».",
            fact_count=n,
        )

    if cmd.kind == "forget_all":
        n = await asyncio.to_thread(store.delete_all, user_id=user_id)
        return MemoryCommandResult(
            kind="forget_all",
            reply_text=f"Очистил всю память обо мне: {n} запис{'ь' if n == 1 else 'и/ей'}.",
            fact_count=n,
        )

    if cmd.kind == "recall_all":
        facts = await asyncio.to_thread(store.list_facts, user_id=user_id, limit=50)
        if not facts:
            return MemoryCommandResult(
                kind="recall_all",
                reply_text="Я пока ничего о вас не помню. Скажите «запомни, что …», и я сохраню факт.",
                fact_count=0,
            )
        lines = ["Вот что я помню о вас:", ""]
        for f in facts:
            lines.append(f"- {f.content}")
        return MemoryCommandResult(
            kind="recall_all",
            reply_text="\n".join(lines),
            fact_count=len(facts),
        )

    # Should never reach here.
    raise ValueError(f"unknown memory command kind: {cmd.kind}")


def build_memory_chat_completion(model_label: str, text: str) -> dict[str, Any]:
    return _chat_completion(model_label, text)


# ---------------------------------------------------------------------------
# Retrieval (RAG-style injection for normal chat)
# ---------------------------------------------------------------------------


async def retrieve_memory_context(
    *,
    store: MemoryStore,
    user_id: str,
    query_text: str,
    http: httpx.AsyncClient,
    settings: Settings,
) -> list[MemoryFact]:
    if not query_text.strip():
        return []
    try:
        qv = await embed_one(http, settings=settings, text=query_text)
    except EmbeddingError as e:
        logger.warning("memory_retrieve_embed_failed err=%s", e)
        return []
    pairs = await asyncio.to_thread(
        store.search_by_embedding,
        user_id=user_id,
        query_vec=qv,
        top_k=settings.memory_retrieval_top_k,
        min_score=settings.memory_retrieval_min_score,
    )
    return [f for f, _score in pairs]


def build_memory_system_message(facts: list[MemoryFact]) -> dict[str, Any] | None:
    if not facts:
        return None
    lines = ["## GPTHub long-term memory (relevant facts)", ""]
    for f in facts:
        lines.append(f"- {f.content}")
    return {"role": "system", "content": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Public facade used by main.py
# ---------------------------------------------------------------------------


def try_parse_command(messages: list[dict[str, Any]]) -> MemoryCommand | None:
    text = last_user_text(messages)
    if not text:
        return None
    return parse_memory_command(text)
