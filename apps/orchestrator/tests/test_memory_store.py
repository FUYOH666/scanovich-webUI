"""MemoryStore: CRUD + embedding search."""

from __future__ import annotations

import pytest

from gpthub_orchestrator.memory.store import MemoryStore, cosine_similarity


@pytest.fixture()
def store(tmp_path) -> MemoryStore:
    s = MemoryStore(tmp_path / "mem.sqlite3")
    try:
        yield s
    finally:
        s.close()


def test_add_and_list(store: MemoryStore):
    store.add_fact(user_id="u1", content="loves Go")
    store.add_fact(user_id="u1", content="drinks espresso")
    facts = store.list_facts(user_id="u1")
    assert len(facts) == 2
    contents = {f.content for f in facts}
    assert contents == {"loves Go", "drinks espresso"}


def test_user_isolation(store: MemoryStore):
    store.add_fact(user_id="u1", content="fact A")
    store.add_fact(user_id="u2", content="fact B")
    assert len(store.list_facts(user_id="u1")) == 1
    assert len(store.list_facts(user_id="u2")) == 1


def test_delete_by_substring(store: MemoryStore):
    store.add_fact(user_id="u1", content="loves Go")
    store.add_fact(user_id="u1", content="loves Rust")
    store.add_fact(user_id="u1", content="drinks coffee")
    n = store.delete_by_substring(user_id="u1", needle="loves")
    assert n == 2
    remaining = store.list_facts(user_id="u1")
    assert len(remaining) == 1
    assert remaining[0].content == "drinks coffee"


def test_delete_all(store: MemoryStore):
    store.add_fact(user_id="u1", content="a")
    store.add_fact(user_id="u1", content="b")
    store.add_fact(user_id="u2", content="c")
    n = store.delete_all(user_id="u1")
    assert n == 2
    assert len(store.list_facts(user_id="u1")) == 0
    assert len(store.list_facts(user_id="u2")) == 1


def test_add_empty_rejected(store: MemoryStore):
    with pytest.raises(ValueError):
        store.add_fact(user_id="u1", content="   ")


def test_search_by_embedding_ranks_by_cosine(store: MemoryStore):
    # Simple 3-dim vectors so we can reason about scoring directly.
    store.add_fact(user_id="u1", content="loves Go", embedding=[1.0, 0.0, 0.0])
    store.add_fact(user_id="u1", content="drinks espresso", embedding=[0.0, 1.0, 0.0])
    store.add_fact(user_id="u1", content="lives in Moscow", embedding=[0.0, 0.0, 1.0])
    results = store.search_by_embedding(
        user_id="u1",
        query_vec=[0.9, 0.1, 0.0],
        top_k=2,
    )
    assert len(results) == 2
    assert results[0][0].content == "loves Go"
    assert results[0][1] > results[1][1]


def test_cosine_similarity_identity():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "mem.sqlite3"
    s1 = MemoryStore(path)
    s1.add_fact(user_id="u1", content="persistent fact")
    s1.close()
    s2 = MemoryStore(path)
    facts = s2.list_facts(user_id="u1")
    s2.close()
    assert len(facts) == 1
    assert facts[0].content == "persistent fact"
