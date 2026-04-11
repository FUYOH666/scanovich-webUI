"""MWS embeddings client (default: qwen3-embedding-8b, dim 4096).

Direct `POST {MWS_GPT_API_BASE}/embeddings` with Bearer key. We do NOT go
through LiteLLM because the alias map is only for chat/vision models and we
want to keep the memory pipeline independent of the chat gateway.
"""

from __future__ import annotations

import logging
from typing import Iterable

import httpx

from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    pass


async def embed_texts(
    http: httpx.AsyncClient,
    *,
    settings: Settings,
    texts: Iterable[str],
) -> list[list[float]]:
    items = [t for t in texts if t and t.strip()]
    if not items:
        return []
    base = settings.mws_gpt_api_base
    key = settings.mws_gpt_api_key
    if not base or not key:
        raise EmbeddingError("mws_credentials_missing")
    url = base.rstrip("/") + "/embeddings"
    payload = {
        "model": settings.memory_embedding_model,
        "input": items,
    }
    try:
        r = await http.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=httpx.Timeout(settings.memory_embedding_timeout_seconds, connect=15.0),
        )
    except httpx.HTTPError as e:
        logger.warning("embedding_http_error err=%s", e)
        raise EmbeddingError(f"http_error: {type(e).__name__}") from e
    if r.status_code >= 400:
        logger.warning("embedding_status status=%s body=%s", r.status_code, r.text[:400])
        raise EmbeddingError(f"status_{r.status_code}")
    try:
        data = r.json()
    except Exception as e:  # noqa: BLE001
        raise EmbeddingError("invalid_json") from e
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise EmbeddingError("empty_data")
    vectors: list[list[float]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise EmbeddingError("bad_row")
        emb = row.get("embedding")
        if not isinstance(emb, list):
            raise EmbeddingError("bad_embedding")
        vectors.append([float(x) for x in emb])
    if len(vectors) != len(items):
        raise EmbeddingError("dim_mismatch")
    return vectors


async def embed_one(
    http: httpx.AsyncClient,
    *,
    settings: Settings,
    text: str,
) -> list[float]:
    vecs = await embed_texts(http, settings=settings, texts=[text])
    if not vecs:
        raise EmbeddingError("empty_result")
    return vecs[0]
