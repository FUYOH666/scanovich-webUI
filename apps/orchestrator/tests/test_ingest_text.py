"""Tests for plain-text (TXT/MD/JSON/code) file ingest."""

from __future__ import annotations

import base64

import httpx
import pytest

from gpthub_orchestrator.ingest.pipeline import run_ingest_pipeline
from gpthub_orchestrator.settings import Settings


def _mk_settings() -> Settings:
    return Settings(  # type: ignore[arg-type]
        litellm_base_url="http://litellm:4000",
        orchestrator_api_key="test",
    )


def _file_part(filename: str, mime: str, raw: bytes) -> dict:
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return {
        "type": "file",
        "file": {
            "filename": filename,
            "file_data": f"data:{mime};base64,{b64}",
        },
    }


@pytest.mark.asyncio
async def test_txt_ingest_creates_document_artifact():
    raw = "This is a plain text document.\nSecond line.".encode("utf-8")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Summarize this file."},
                _file_part("notes.txt", "text/plain", raw),
            ],
        }
    ]
    async with httpx.AsyncClient() as http:
        new_msgs, artifacts, ms = await run_ingest_pipeline(messages, _mk_settings(), http)
    assert ms is not None
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "document_text"
    assert artifacts[0]["title"] == "notes.txt"
    assert "Second line." in artifacts[0]["content"]
    assert new_msgs[0]["role"] == "system"


@pytest.mark.asyncio
async def test_md_ingest_by_extension_even_with_octet_stream_mime():
    raw = b"# Title\n\nHello **world**."
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what's in this?"},
                _file_part("readme.md", "application/octet-stream", raw),
            ],
        }
    ]
    async with httpx.AsyncClient() as http:
        new_msgs, artifacts, ms = await run_ingest_pipeline(messages, _mk_settings(), http)
    assert ms is not None
    assert len(artifacts) == 1
    assert artifacts[0]["content"].startswith("# Title")


@pytest.mark.asyncio
async def test_json_file_ingested_as_text():
    raw = b'{"k": "v", "n": 1}'
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "parse"},
                _file_part("payload.json", "application/json", raw),
            ],
        }
    ]
    async with httpx.AsyncClient() as http:
        _, artifacts, _ = await run_ingest_pipeline(messages, _mk_settings(), http)
    assert len(artifacts) == 1
    assert '"k": "v"' in artifacts[0]["content"]
