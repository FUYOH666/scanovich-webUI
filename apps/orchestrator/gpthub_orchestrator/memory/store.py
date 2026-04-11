"""SQLite-backed long-term memory store.

Schema is intentionally minimal:

    CREATE TABLE memory_facts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      TEXT NOT NULL,
        content      TEXT NOT NULL,
        embedding    BLOB,            -- packed float32, optional
        created_at   REAL NOT NULL,   -- unix seconds
        updated_at   REAL NOT NULL
    );

Vectors are stored as raw little-endian float32 bytes so the row does not bloat
with JSON overhead and similarity scoring can run on numpy/array arithmetic.

All operations are synchronous; async callers must offload to a thread (e.g.
`asyncio.to_thread`).
"""

from __future__ import annotations

import array
import math
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   BLOB,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS memory_facts_user_idx ON memory_facts(user_id);
"""


@dataclass
class MemoryFact:
    id: int
    user_id: str
    content: str
    embedding: tuple[float, ...] | None
    created_at: float
    updated_at: float


def _pack_vec(vec: Iterable[float] | None) -> bytes | None:
    if vec is None:
        return None
    arr = array.array("f", [float(x) for x in vec])
    return arr.tobytes()


def _unpack_vec(blob: bytes | None) -> tuple[float, ...] | None:
    if blob is None:
        return None
    arr = array.array("f")
    arr.frombytes(blob)
    return tuple(arr)


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    ax = list(a)
    bx = list(b)
    if not ax or not bx or len(ax) != len(bx):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(ax, bx, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class MemoryStore:
    """Thread-safe SQLite fact store.

    A single connection is shared (check_same_thread=False) under an internal
    lock; that is sufficient for the orchestrator where concurrent writes are
    rare and writes are short.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        need_parent = self._path not in (":memory:", "")
        if need_parent:
            parent = Path(self._path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self._path,
            check_same_thread=False,
            isolation_level=None,  # autocommit — every statement is its own txn
        )
        with self._lock:
            self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ writes
    def add_fact(
        self,
        *,
        user_id: str,
        content: str,
        embedding: Iterable[float] | None = None,
    ) -> MemoryFact:
        content = content.strip()
        if not content:
            raise ValueError("empty_content")
        now = time.time()
        blob = _pack_vec(embedding)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO memory_facts(user_id, content, embedding, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (user_id, content, blob, now, now),
            )
            fid = int(cur.lastrowid or 0)
        return MemoryFact(
            id=fid,
            user_id=user_id,
            content=content,
            embedding=tuple(embedding) if embedding is not None else None,
            created_at=now,
            updated_at=now,
        )

    def delete_by_id(self, *, user_id: str, fact_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memory_facts WHERE id = ? AND user_id = ?",
                (fact_id, user_id),
            )
            return (cur.rowcount or 0) > 0

    def delete_by_substring(self, *, user_id: str, needle: str) -> int:
        needle = needle.strip()
        if not needle:
            return 0
        like = f"%{needle}%"
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memory_facts WHERE user_id = ? AND content LIKE ?",
                (user_id, like),
            )
            return int(cur.rowcount or 0)

    def delete_all(self, *, user_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memory_facts WHERE user_id = ?",
                (user_id,),
            )
            return int(cur.rowcount or 0)

    # ------------------------------------------------------------------- reads
    def list_facts(self, *, user_id: str, limit: int = 50) -> list[MemoryFact]:
        limit = max(1, min(1000, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, user_id, content, embedding, created_at, updated_at"
                " FROM memory_facts WHERE user_id = ?"
                " ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            MemoryFact(
                id=int(r[0]),
                user_id=str(r[1]),
                content=str(r[2]),
                embedding=_unpack_vec(r[3]),
                created_at=float(r[4]),
                updated_at=float(r[5]),
            )
            for r in rows
        ]

    def search_by_embedding(
        self,
        *,
        user_id: str,
        query_vec: Iterable[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[tuple[MemoryFact, float]]:
        qv = list(query_vec)
        if not qv:
            return []
        facts = self.list_facts(user_id=user_id, limit=1000)
        scored: list[tuple[MemoryFact, float]] = []
        for f in facts:
            if f.embedding is None:
                continue
            score = cosine_similarity(qv, f.embedding)
            if score >= min_score:
                scored.append((f, score))
        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[: max(1, int(top_k))]

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
