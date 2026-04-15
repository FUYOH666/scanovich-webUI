"""Normalize BGE-M3 hybrid /v1/embeddings to OpenAI shape (field `embedding`).

Open WebUI RAG expects each item in data[] to have `embedding`: float[].
Hybrid BGE often returns `dense_embedding` instead.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response

logger = logging.getLogger("gpthub_embedding_shim")

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


def _embeddings_request_digest(raw: bytes) -> dict:
    out: dict = {"raw_bytes": len(raw)}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        out["json_error"] = str(e)
        return out
    if not isinstance(payload, dict):
        out["body_kind"] = type(payload).__name__
        return out
    model = payload.get("model")
    if model is not None:
        out["model"] = model
    inp = payload.get("input")
    if isinstance(inp, str):
        out["input_kind"] = "str"
        out["input_len"] = len(inp)
        out["input_sha256_16"] = hashlib.sha256(inp.encode("utf-8", errors="replace")).hexdigest()[:16]
    elif isinstance(inp, list):
        out["input_kind"] = "list"
        out["input_n"] = len(inp)
        lens: list[int] = []
        for i, x in enumerate(inp[:32]):
            if isinstance(x, str):
                lens.append(len(x))
            else:
                lens.append(-1)
        out["input_lens_head"] = lens
        if len(inp) > 32:
            out["input_lens_truncated_after"] = 32
    else:
        out["input_kind"] = type(inp).__name__ if inp is not None else "null"
    # Log full JSON for small bodies; otherwise digest only (avoid megabyte log lines).
    raw_s = json.dumps(payload, ensure_ascii=False)
    if len(raw_s) <= 48_000:
        out["body_json"] = raw_s
    else:
        out["body_json_omitted_len"] = len(raw_s)
    return out


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> Response:
    body = await request.body()
    auth = request.headers.get("authorization", "")
    ct_in = request.headers.get("content-type", "application/json")
    digest = _embeddings_request_digest(body)
    logger.info(
        "embeddings_in upstream_url=%s content_type=%s %s",
        EMBEDDINGS_URL,
        ct_in,
        json.dumps(digest, ensure_ascii=False, default=str),
    )
    client: httpx.AsyncClient = request.app.state.http
    try:
        r = await client.post(
            EMBEDDINGS_URL,
            content=body,
            headers={
                "Content-Type": ct_in,
                "Authorization": auth,
            },
        )
    except httpx.HTTPError as e:
        logger.warning("embeddings_upstream_http_error err=%s req_bytes=%s", e, len(body))
        err = json.dumps({"error": {"message": f"upstream_unreachable: {type(e).__name__}: {e}"}}).encode("utf-8")
        return Response(content=err, status_code=502, media_type="application/json")
    try:
        resp_snip = (r.text or "")[:800]
    except Exception:  # noqa: BLE001
        resp_snip = repr(r.content[:200])
    logger.info(
        "embeddings_out status=%s resp_bytes=%s snippet=%s",
        r.status_code,
        len(r.content),
        resp_snip,
    )
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
