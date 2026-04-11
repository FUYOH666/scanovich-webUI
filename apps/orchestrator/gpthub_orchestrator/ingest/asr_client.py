"""Call OpenAI-compatible ASR (transcriptions)."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class AsrError(Exception):
    pass


async def transcribe_audio_bytes(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    model: str,
    data: bytes,
    filename: str,
    content_type: str,
) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        url = f"{base}/audio/transcriptions"
    else:
        url = f"{base}/v1/audio/transcriptions"
    try:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, data, content_type)},
            data={"model": model},
            timeout=httpx.Timeout(120.0, connect=30.0),
        )
    except httpx.HTTPError as e:
        logger.warning("asr_request_failed err=%s", e)
        raise AsrError("asr_connection") from e
    if r.status_code >= 400:
        logger.warning("asr_upstream status=%s body=%s", r.status_code, r.text[:400])
        raise AsrError(f"asr_status_{r.status_code}")
    try:
        payload = r.json()
    except Exception as e:
        raise AsrError("asr_invalid_json") from e
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise AsrError("asr_empty_transcript")
    return text.strip()
