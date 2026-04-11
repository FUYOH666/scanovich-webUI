"""Tests for URL ingest: detection, SSRF, fetch, pipeline integration."""

from __future__ import annotations

import httpx
import pytest

from gpthub_orchestrator.ingest.pipeline import run_ingest_pipeline
from gpthub_orchestrator.ingest.url_fetch import (
    UrlFetchError,
    extract_urls_from_message_content,
    extract_urls_from_text,
    fetch_url_text,
    html_to_text,
)
from gpthub_orchestrator.settings import Settings


def _mk_settings(**overrides) -> Settings:
    base = {
        "litellm_base_url": "http://litellm:4000",
        "orchestrator_api_key": "test",
        "ingest_url_allow_private_hosts": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------


def test_extract_urls_from_text_basic():
    text = "see https://example.com/a and http://foo.bar/baz?q=1 please"
    urls = extract_urls_from_text(text, limit=5)
    assert urls == ["https://example.com/a", "http://foo.bar/baz?q=1"]


def test_extract_urls_strips_trailing_punctuation():
    text = "open https://example.com/path."
    urls = extract_urls_from_text(text, limit=5)
    assert urls == ["https://example.com/path"]


def test_extract_urls_dedup_and_limit():
    text = "a https://x.test/1 b https://x.test/1 c https://y.test/2 d https://z.test/3"
    urls = extract_urls_from_text(text, limit=2)
    assert urls == ["https://x.test/1", "https://y.test/2"]


def test_extract_urls_from_content_parts_list():
    content = [
        {"type": "text", "text": "check https://one.test"},
        {"type": "image_url", "image_url": {"url": "https://should-be-ignored.test"}},
        {"type": "text", "text": "and also https://two.test"},
    ]
    urls = extract_urls_from_message_content(content, limit=5)
    assert urls == ["https://one.test", "https://two.test"]


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


def test_html_to_text_basic():
    html = """
    <html><head><title>Hi there</title><style>body {color:red}</style></head>
    <body><h1>Hello</h1><script>var x=1;</script>
    <p>First para.</p><p>Second para.</p></body></html>
    """
    title, text = html_to_text(html)
    assert title == "Hi there"
    assert "Hello" in text
    assert "First para." in text
    assert "Second para." in text
    assert "var x" not in text
    assert "color:red" not in text


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_url_blocks_private_by_default():
    async with httpx.AsyncClient() as http:
        with pytest.raises(UrlFetchError):
            await fetch_url_text(
                http,
                "http://127.0.0.1:1/",
                timeout_seconds=2.0,
                max_bytes=1000,
                allow_private=False,
            )


@pytest.mark.asyncio
async def test_fetch_url_rejects_non_http_scheme():
    async with httpx.AsyncClient() as http:
        with pytest.raises(UrlFetchError):
            await fetch_url_text(
                http,
                "file:///etc/passwd",
                timeout_seconds=2.0,
                max_bytes=1000,
                allow_private=True,
            )


# ---------------------------------------------------------------------------
# Fetch happy path with MockTransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_url_extracts_html_title_and_text():
    html = "<html><head><title>Doc</title></head><body><p>Hello world.</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/post"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=html.encode("utf-8"),
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        art = await fetch_url_text(
            http,
            "https://example.test/post",
            timeout_seconds=5.0,
            max_bytes=100_000,
            allow_private=True,
        )
    assert art.title == "Doc"
    assert "Hello world." in art.text


@pytest.mark.asyncio
async def test_fetch_url_size_limit_enforced():
    big = b"<html><body>" + (b"A" * 10_000) + b"</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=big,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(UrlFetchError):
            await fetch_url_text(
                http,
                "https://example.test/",
                timeout_seconds=5.0,
                max_bytes=500,
                allow_private=True,
            )


@pytest.mark.asyncio
async def test_fetch_url_rejects_unsupported_content_type():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/octet-stream"},
            content=b"binary",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(UrlFetchError):
            await fetch_url_text(
                http,
                "https://example.test/blob",
                timeout_seconds=5.0,
                max_bytes=1000,
                allow_private=True,
            )


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_injects_url_artifact_and_runs_without_files():
    html = "<html><head><title>Page</title></head><body><p>Body text.</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=html.encode("utf-8"),
        )

    transport = httpx.MockTransport(handler)
    settings = _mk_settings()

    messages = [
        {"role": "user", "content": "look at https://example.test/news"},
    ]
    async with httpx.AsyncClient(transport=transport) as http:
        new_messages, artifacts, ms = await run_ingest_pipeline(messages, settings, http)

    assert ms is not None and ms >= 0
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "url_text"
    # First message is the injected system block
    assert new_messages[0]["role"] == "system"
    assert "Body text." in new_messages[0]["content"]
    # The user message text is preserved intact (URL ingest does NOT strip the URL)
    assert new_messages[1]["role"] == "user"
    assert "https://example.test/news" in new_messages[1]["content"]


@pytest.mark.asyncio
async def test_pipeline_noop_when_no_urls_and_no_files():
    settings = _mk_settings()
    messages = [{"role": "user", "content": "just a text question"}]
    async with httpx.AsyncClient() as http:
        new_messages, artifacts, ms = await run_ingest_pipeline(messages, settings, http)
    assert new_messages is messages
    assert artifacts == []
    assert ms is None
