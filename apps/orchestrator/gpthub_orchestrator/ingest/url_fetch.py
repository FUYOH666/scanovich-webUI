"""Fetch and extract plain text from URLs referenced in the last user message.

Scope: hackathon baseline. Zero extra deps — stdlib HTML parser + httpx.
Hard limits: timeout, max bytes, max redirects, SSRF block on private IPs.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}>\u2019\u201d"


def _is_pptx_artifact_download_url(url: str) -> bool:
    """GET on these URLs consumes a one-time token (see main.download_pptx_artifact)."""
    try:
        parsed = urlparse(url.strip())
        return "/artifacts/pptx/" in (parsed.path or "").lower()
    except Exception:
        return False


class UrlFetchError(Exception):
    pass


@dataclass
class UrlArtifact:
    url: str
    title: str
    text: str


def extract_urls_from_text(text: str, *, limit: int) -> list[str]:
    """Return up to `limit` unique URLs from a text blob, preserving order."""
    if not text or limit <= 0:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in _URL_RE.findall(text):
        cleaned = raw.rstrip(_TRAILING_PUNCT)
        if _is_pptx_artifact_download_url(cleaned):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def extract_urls_from_message_content(
    content: str | list[object],
    *,
    limit: int,
) -> list[str]:
    """Scan OpenAI-style content (string or list of parts) for URLs in text parts."""
    if limit <= 0:
        return []
    if isinstance(content, str):
        return extract_urls_from_text(content, limit=limit)
    found: list[str] = []
    seen: set[str] = set()
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") != "text":
                continue
            t = part.get("text")
            if not isinstance(t, str):
                continue
            for u in extract_urls_from_text(t, limit=limit):
                if u in seen:
                    continue
                seen.add(u)
                found.append(u)
                if len(found) >= limit:
                    return found
    return found


def _is_private_host(host: str) -> bool:
    """True if host resolves to a private, loopback, link-local, or reserved IP."""
    host = (host or "").strip().lower()
    if not host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True
    for info in infos:
        addr = info[4][0]
        # strip scope id from IPv6
        addr = addr.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def _validate_url_for_fetch(url: str, *, allow_private: bool) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlFetchError(f"unsupported scheme: {parsed.scheme or 'empty'}")
    host = parsed.hostname or ""
    if not host:
        raise UrlFetchError("missing host")
    if not allow_private and _is_private_host(host):
        raise UrlFetchError(f"blocked private host: {host}")
    return host


class _TextCollector(HTMLParser):
    """Minimal HTML-to-text collector. Skips script/style; records <title>."""

    _SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
    _BLOCK_TAGS = {
        "p",
        "br",
        "div",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "header",
        "footer",
        "hr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if t == "title":
            self._in_title = True
            return
        if t in self._BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if t == "title":
            self._in_title = False
            return
        if t in self._BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        self.text_parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    """Return (title, plain_text). Title can be empty."""
    parser = _TextCollector()
    try:
        parser.feed(html)
    except Exception as e:  # noqa: BLE001 - HTMLParser can raise on malformed chunks
        logger.debug("html_parser_failed err=%s", e)
    title = " ".join(t.strip() for t in parser.title_parts).strip()
    raw_text = "".join(parser.text_parts)
    # collapse whitespace, preserving paragraph breaks
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw_text.splitlines()]
    compact: list[str] = []
    blank = False
    for ln in lines:
        if ln:
            compact.append(ln)
            blank = False
        elif not blank:
            compact.append("")
            blank = True
    return title, "\n".join(compact).strip()


async def fetch_url_text(
    http: httpx.AsyncClient,
    url: str,
    *,
    timeout_seconds: float,
    max_bytes: int,
    allow_private: bool = False,
) -> UrlArtifact:
    """Fetch URL and return plain-text artifact. Raises UrlFetchError on any issue."""
    _validate_url_for_fetch(url, allow_private=allow_private)
    timeout = httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds))
    try:
        async with http.stream(
            "GET",
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "GPTHub-Orchestrator/0.1 (+ingest-url)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
            },
        ) as resp:
            if resp.status_code >= 400:
                raise UrlFetchError(f"http_status_{resp.status_code}")
            # Post-redirect host re-check (httpx resolved through chain, still verify final host)
            final_host = resp.url.host or ""
            if not allow_private and _is_private_host(final_host):
                raise UrlFetchError(f"blocked private redirect host: {final_host}")
            ct = (resp.headers.get("content-type") or "").lower()
            if ct and not any(
                ct.startswith(prefix) for prefix in ("text/", "application/xhtml", "application/json")
            ):
                raise UrlFetchError(f"unsupported content-type: {ct}")
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise UrlFetchError(f"response exceeds {max_bytes} bytes")
            body_bytes = bytes(buf)
    except httpx.TimeoutException as e:
        raise UrlFetchError("timeout") from e
    except httpx.HTTPError as e:
        raise UrlFetchError(f"http_error: {type(e).__name__}") from e

    # Decode
    encoding = resp.encoding or "utf-8"
    try:
        html = body_bytes.decode(encoding, errors="replace")
    except LookupError:
        html = body_bytes.decode("utf-8", errors="replace")

    if "text/html" in ct or "xhtml" in ct or html.lstrip().startswith("<"):
        title, text = html_to_text(html)
    else:
        title = ""
        text = html
    if not text.strip():
        raise UrlFetchError("empty_text_after_extract")
    return UrlArtifact(url=str(resp.url), title=title, text=text)
