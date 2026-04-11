"""Normalize BGE-M3 hybrid /v1/embeddings to OpenAI shape (field `embedding`).

Open WebUI RAG expects each item in data[] to have `embedding`: float[].
Hybrid BGE often returns `dense_embedding` instead.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response

_RAW_UPSTREAM = (
    os.environ.get("BGE_EMBEDDING_UPSTREAM", "").strip()
    or os.environ.get("MWS_GPT_API_BASE", "").strip()
    or "http://host.docker.internal:9001"
).strip()


def _embeddings_url(upstream: str) -> str:
    """Match orchestrator: MWS_GPT_API_BASE is usually .../v1 → POST .../v1/embeddings."""
    u = upstream.rstrip("/")
    if u.endswith("/v1"):
        return f"{u}/embeddings"
    return f"{u}/v1/embeddings"


EMBEDDINGS_URL = _embeddings_url(_RAW_UPSTREAM)


@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.http = client
        yield


app = FastAPI(title="gpthub-prod embedding shim", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "gpthub-prod-embedding-shim"}


def _normalize_payload(data: dict) -> dict:
    items = data.get("data")
    if not isinstance(items, list):
        return data
    for item in items:
        if not isinstance(item, dict):
            continue
        if "embedding" not in item and "dense_embedding" in item:
            item["embedding"] = item["dense_embedding"]
    return data


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> Response:
    body = await request.body()
    auth = request.headers.get("authorization", "")
    client: httpx.AsyncClient = request.app.state.http
    try:
        r = await client.post(
            EMBEDDINGS_URL,
            content=body,
            headers={
                "Content-Type": request.headers.get("content-type", "application/json"),
                "Authorization": auth,
            },
        )
    except httpx.HTTPError as e:
        err = json.dumps({"error": {"message": f"upstream_unreachable: {type(e).__name__}: {e}"}}).encode("utf-8")
        return Response(content=err, status_code=502, media_type="application/json")
    ct = r.headers.get("content-type", "application/json")
    if r.status_code >= 400 or "json" not in ct.lower():
        return Response(content=r.content, status_code=r.status_code, media_type=ct)
    try:
        payload = r.json()
    except json.JSONDecodeError:
        return Response(content=r.content, status_code=r.status_code, media_type=ct)
    if isinstance(payload, dict):
        payload = _normalize_payload(payload)
    raw = json.dumps(payload).encode("utf-8")
    return Response(content=raw, status_code=r.status_code, media_type="application/json")
