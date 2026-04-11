"""Memory service: embeddings client + end-to-end command execution."""

from __future__ import annotations

import httpx
import pytest

from gpthub_orchestrator.memory.commands import MemoryCommand
from gpthub_orchestrator.memory.embeddings import EmbeddingError, embed_one, embed_texts
from gpthub_orchestrator.memory.service import (
    build_memory_system_message,
    execute_memory_command,
    last_user_text,
    resolve_user_id,
    retrieve_memory_context,
    try_parse_command,
)
from gpthub_orchestrator.memory.store import MemoryStore
from gpthub_orchestrator.settings import Settings


def _mk_settings(**over) -> Settings:
    base = {
        "litellm_base_url": "http://litellm:4000",
        "orchestrator_api_key": "t",
        "mws_gpt_api_base": "https://api.gpt.mws.ru/v1",
        "mws_gpt_api_key": "sk-test",
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture()
def store(tmp_path) -> MemoryStore:
    s = MemoryStore(tmp_path / "svc.sqlite3")
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_last_user_text_from_string():
    assert last_user_text([{"role": "user", "content": "hello"}]) == "hello"


def test_last_user_text_from_parts():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "part one"},
            {"type": "text", "text": "part two"},
        ],
    }
    assert last_user_text([msg]) == "part one part two"


def test_resolve_user_id_default():
    assert resolve_user_id([{"role": "user", "content": "hi"}]) == "default"


def test_try_parse_command_picks_last_user():
    msgs = [
        {"role": "user", "content": "просто вопрос"},
        {"role": "assistant", "content": "ответ"},
        {"role": "user", "content": "Запомни, что я пью чай"},
    ]
    cmd = try_parse_command(msgs)
    assert cmd is not None
    assert cmd.kind == "remember"
    assert cmd.payload == "я пью чай"


# ---------------------------------------------------------------------------
# Embeddings client
# ---------------------------------------------------------------------------


def _embedding_handler(vec: list[float]):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        body = request.read()
        assert b"qwen3-embedding-8b" in body
        return httpx.Response(
            200,
            json={"data": [{"embedding": vec}]},
        )

    return handler


@pytest.mark.asyncio
async def test_embed_one_happy_path():
    transport = httpx.MockTransport(_embedding_handler([0.1, 0.2, 0.3]))
    async with httpx.AsyncClient(transport=transport) as http:
        vec = await embed_one(http, settings=_mk_settings(), text="hello")
    assert vec == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_embed_texts_batches_inputs():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["payload"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={"data": [{"embedding": [1.0]}, {"embedding": [2.0]}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        vecs = await embed_texts(http, settings=_mk_settings(), texts=["a", "b"])
    assert vecs == [[1.0], [2.0]]
    assert captured["payload"]["input"] == ["a", "b"]


@pytest.mark.asyncio
async def test_embed_one_missing_credentials():
    async with httpx.AsyncClient() as http:
        with pytest.raises(EmbeddingError):
            await embed_one(
                http,
                settings=_mk_settings(mws_gpt_api_base=None, mws_gpt_api_key=None),
                text="hi",
            )


@pytest.mark.asyncio
async def test_embed_one_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(EmbeddingError):
            await embed_one(http, settings=_mk_settings(), text="hi")


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remember_command_stores_fact(store: MemoryStore):
    transport = httpx.MockTransport(_embedding_handler([0.5, 0.5, 0.0]))
    async with httpx.AsyncClient(transport=transport) as http:
        result = await execute_memory_command(
            MemoryCommand(kind="remember", payload="я люблю Go"),
            store=store,
            user_id="u1",
            http=http,
            settings=_mk_settings(),
        )
    assert result.kind == "remember"
    assert "Запомнил" in result.reply_text
    facts = store.list_facts(user_id="u1")
    assert len(facts) == 1
    assert facts[0].content == "я люблю Go"
    assert facts[0].embedding is not None


@pytest.mark.asyncio
async def test_remember_command_survives_embedding_failure(store: MemoryStore):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        result = await execute_memory_command(
            MemoryCommand(kind="remember", payload="offline fact"),
            store=store,
            user_id="u1",
            http=http,
            settings=_mk_settings(),
        )
    assert result.kind == "remember"
    facts = store.list_facts(user_id="u1")
    assert len(facts) == 1
    assert facts[0].embedding is None  # embedding failed but fact is kept


@pytest.mark.asyncio
async def test_forget_command(store: MemoryStore):
    store.add_fact(user_id="u1", content="loves espresso")
    store.add_fact(user_id="u1", content="loves tea")
    async with httpx.AsyncClient() as http:
        result = await execute_memory_command(
            MemoryCommand(kind="forget", payload="espresso"),
            store=store,
            user_id="u1",
            http=http,
            settings=_mk_settings(),
        )
    assert result.kind == "forget"
    assert result.fact_count == 1
    remaining = store.list_facts(user_id="u1")
    assert len(remaining) == 1
    assert remaining[0].content == "loves tea"


@pytest.mark.asyncio
async def test_forget_all_command(store: MemoryStore):
    store.add_fact(user_id="u1", content="a")
    store.add_fact(user_id="u1", content="b")
    async with httpx.AsyncClient() as http:
        result = await execute_memory_command(
            MemoryCommand(kind="forget_all", payload=""),
            store=store,
            user_id="u1",
            http=http,
            settings=_mk_settings(),
        )
    assert result.fact_count == 2
    assert store.list_facts(user_id="u1") == []


@pytest.mark.asyncio
async def test_recall_all_empty(store: MemoryStore):
    async with httpx.AsyncClient() as http:
        result = await execute_memory_command(
            MemoryCommand(kind="recall_all", payload=""),
            store=store,
            user_id="u1",
            http=http,
            settings=_mk_settings(),
        )
    assert result.fact_count == 0
    assert "ничего" in result.reply_text.lower()


@pytest.mark.asyncio
async def test_recall_all_with_facts(store: MemoryStore):
    store.add_fact(user_id="u1", content="loves Go")
    store.add_fact(user_id="u1", content="drinks espresso")
    async with httpx.AsyncClient() as http:
        result = await execute_memory_command(
            MemoryCommand(kind="recall_all", payload=""),
            store=store,
            user_id="u1",
            http=http,
            settings=_mk_settings(),
        )
    assert result.fact_count == 2
    assert "loves Go" in result.reply_text
    assert "drinks espresso" in result.reply_text


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_memory_context_ranks_and_filters(store: MemoryStore):
    store.add_fact(user_id="u1", content="loves Go", embedding=[1.0, 0.0, 0.0])
    store.add_fact(user_id="u1", content="drinks espresso", embedding=[0.0, 1.0, 0.0])
    store.add_fact(user_id="u1", content="lives in Moscow", embedding=[0.0, 0.0, 1.0])

    transport = httpx.MockTransport(_embedding_handler([0.95, 0.05, 0.0]))
    async with httpx.AsyncClient(transport=transport) as http:
        facts = await retrieve_memory_context(
            store=store,
            user_id="u1",
            query_text="What language does the user prefer?",
            http=http,
            settings=_mk_settings(
                memory_retrieval_top_k=2,
                memory_retrieval_min_score=0.0,
            ),
        )
    assert len(facts) == 2
    assert facts[0].content == "loves Go"


@pytest.mark.asyncio
async def test_retrieve_memory_context_returns_empty_on_embedding_failure(store: MemoryStore):
    store.add_fact(user_id="u1", content="loves Go", embedding=[1.0, 0.0, 0.0])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        facts = await retrieve_memory_context(
            store=store,
            user_id="u1",
            query_text="anything",
            http=http,
            settings=_mk_settings(),
        )
    assert facts == []


def test_build_memory_system_message_empty():
    assert build_memory_system_message([]) is None
