"""Run ingest on the last user message and inject artifacts as a client system block."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
from typing import Any

import httpx

from gpthub_orchestrator.ingest.asr_client import AsrError, transcribe_audio_bytes
from gpthub_orchestrator.ingest.parts import (
    FileWorkItem,
    extract_file_work_items,
    last_user_message_index,
    strip_content_indices,
)
from gpthub_orchestrator.ingest.pdf_extract import PdfExtractError, parse_pdf_bytes
from gpthub_orchestrator.ingest.richdoc import (
    RichDocConvertError,
    convert_richdoc_bytes,
    is_richdoc_item,
)
from gpthub_orchestrator.ingest.url_fetch import (
    UrlFetchError,
    extract_urls_from_message_content,
    fetch_url_text,
)
from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)

_ARTIFACT_CONTENT_CAP = 24_000


def _file_items_summary(indexed_items: list[tuple[int, Any]]) -> str:
    return json.dumps(
        [
            {"part_idx": i, "filename": w.filename, "mime": w.mime, "raw_bytes": len(w.raw)}
            for i, w in indexed_items
        ],
        ensure_ascii=False,
    )


def _is_audio_item(mime: str, filename: str) -> bool:
    if mime.startswith("audio/"):
        return True
    low = filename.lower()
    return low.endswith((".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"))


_PLAIN_TEXT_SUFFIXES = (
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".tsv",
    ".log",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".ini",
    ".toml",
    ".html",
    ".htm",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".sql",
    ".sh",
)


def _is_plain_text_item(mime: str, filename: str) -> bool:
    if mime.startswith("text/"):
        return True
    if mime in (
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
        "application/toml",
        "application/javascript",
        "application/x-sh",
    ):
        return True
    low = filename.lower()
    return low.endswith(_PLAIN_TEXT_SUFFIXES)


def _convert_richdoc_sync(item: FileWorkItem) -> str:
    try:
        return convert_richdoc_bytes(item.raw, filename=item.filename)
    except RichDocConvertError as e:
        logger.warning("richdoc_ingest_failed file=%s err=%s", item.filename, e)
        return f"[Rich document could not be converted: {e}]"


async def _process_one_richdoc(item: FileWorkItem) -> dict[str, Any]:
    text = await asyncio.to_thread(_convert_richdoc_sync, item)
    if len(text) > _ARTIFACT_CONTENT_CAP:
        text = text[:_ARTIFACT_CONTENT_CAP] + "\n… [truncated by orchestrator]"
    return {"type": "document_text", "title": item.filename, "content": text}


async def _process_one_plain_text(item: FileWorkItem) -> dict[str, Any]:
    try:
        text = item.raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = item.raw.decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            logger.warning("text_decode_failed file=%s err=%s", item.filename, e)
            return {
                "type": "document_text",
                "title": item.filename,
                "content": f"[text file could not be decoded: {e}]",
            }
    if len(text) > _ARTIFACT_CONTENT_CAP:
        text = text[:_ARTIFACT_CONTENT_CAP] + "\n… [truncated by orchestrator]"
    return {"type": "document_text", "title": item.filename, "content": text}


def _artifact_for_trace(a: dict[str, Any]) -> dict[str, Any]:
    """Smaller payload for trace header."""
    out = dict(a)
    c = out.get("content")
    if isinstance(c, str) and len(c) > 2000:
        out["content"] = c[:2000] + f"\n… [{len(c) - 2000} chars truncated for trace]"
    return out


def _build_artifact_system_message(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    lines = ["## GPTHub ingested context (orchestrator)", ""]
    for a in artifacts:
        t = a.get("type")
        title = a.get("title", "")
        content = a.get("content", "")
        lines.append(f"### {t}: {title}")
        lines.append(str(content))
        lines.append("")
    body = "\n".join(lines).strip()
    return {"role": "system", "content": body}


def _parse_pdf_sync(item: FileWorkItem, settings: Settings) -> str:
    try:
        return parse_pdf_bytes(
            item.raw,
            max_bytes=settings.ingest_pdf_max_bytes,
            max_pages=settings.ingest_pdf_max_pages,
        )
    except PdfExtractError as e:
        logger.warning("pdf_ingest_failed file=%s err=%s", item.filename, e)
        return f"[PDF could not be extracted: {e}]"


async def _process_one_pdf(item: FileWorkItem, settings: Settings) -> dict[str, Any]:
    text = await asyncio.to_thread(_parse_pdf_sync, item, settings)
    if len(text) > _ARTIFACT_CONTENT_CAP:
        text = text[:_ARTIFACT_CONTENT_CAP] + "\n… [truncated by orchestrator]"
    return {"type": "document_text", "title": item.filename, "content": text}


async def _process_one_audio(
    item: FileWorkItem,
    settings: Settings,
    http: httpx.AsyncClient,
) -> dict[str, Any]:
    base_url = settings.resolved_asr_base_url()
    api_key = settings.resolved_asr_api_key()
    ct = item.mime if "/" in item.mime else "application/octet-stream"
    logger.info(
        "asr_ingest_start filename=%s mime=%s bytes=%s asr_base_configured=%s",
        item.filename,
        ct,
        len(item.raw),
        bool(base_url and api_key),
    )
    if not base_url or not api_key:
        logger.warning(
            "asr_ingest_skipped_missing_credentials filename=%s hint=ORCHESTRATOR_ASR_*_or_MWS_GPT_API_*",
            item.filename,
        )
        return {
            "type": "transcript",
            "title": item.filename,
            "content": "[Audio attachment present; set ORCHESTRATOR_ASR_BASE_URL/ASR_API_KEY or MWS_GPT_API_BASE/KEY.]",
        }
    try:
        text = await transcribe_audio_bytes(
            http,
            base_url=base_url,
            api_key=api_key,
            model=settings.orchestrator_asr_model,
            data=item.raw,
            filename=item.filename,
            content_type=ct,
        )
    except AsrError as e:
        logger.warning("asr_ingest_failed file=%s err=%s", item.filename, e)
        text = f"[ASR error: {e}]"
    logger.info(
        "asr_ingest_done filename=%s transcript_chars=%s head=%s",
        item.filename,
        len(text),
        text[:400].replace("\n", "\\n"),
    )
    if len(text) > _ARTIFACT_CONTENT_CAP:
        text = text[:_ARTIFACT_CONTENT_CAP] + "\n… [truncated]"
    return {"type": "transcript", "title": item.filename, "content": text}


async def _process_one_url(url: str, settings: Settings, http: httpx.AsyncClient) -> dict[str, Any]:
    try:
        art = await fetch_url_text(
            http,
            url,
            timeout_seconds=settings.ingest_url_timeout_seconds,
            max_bytes=settings.ingest_url_max_bytes,
            allow_private=settings.ingest_url_allow_private_hosts,
        )
    except UrlFetchError as e:
        logger.warning("url_ingest_failed url=%s err=%s", url, e)
        return {
            "type": "url_text",
            "title": url,
            "content": f"[URL could not be fetched: {e}]",
        }
    text = art.text
    if len(text) > _ARTIFACT_CONTENT_CAP:
        text = text[:_ARTIFACT_CONTENT_CAP] + "\n… [truncated by orchestrator]"
    title = art.title.strip() or art.url
    return {"type": "url_text", "title": title, "content": text}


def _peek_urls(messages: list[dict[str, Any]], settings: Settings) -> list[str]:
    if not settings.ingest_url_enabled:
        return []
    idx = last_user_message_index(messages)
    if idx is None:
        return []
    content = messages[idx].get("content")
    if content is None:
        return []
    return extract_urls_from_message_content(
        content,
        limit=settings.ingest_url_max_per_message,
    )


async def run_ingest_pipeline(
    messages: list[dict[str, Any]],
    settings: Settings,
    http: httpx.AsyncClient,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float | None]:
    """
    Deep-copy messages, extract PDF/audio/URL from last user parts, append artifacts as system message.

    Returns (new_messages, trace_artifacts, ingest_ms).
    """
    if not settings.ingest_enabled:
        pidx, pit = extract_file_work_items(messages)
        logger.info(
            "ingest_disabled ingest_enabled=false peek_user_idx=%s peek_items=%s",
            pidx,
            _file_items_summary(pit) if pit else "[]",
        )
        return messages, [], None

    peek_idx, peek_items = extract_file_work_items(messages)
    peek_urls = _peek_urls(messages, settings)
    logger.info(
        "ingest_peek last_user_msg_idx=%s file_parts=%s urls=%s",
        peek_idx,
        _file_items_summary(peek_items) if peek_items else "[]",
        json.dumps(peek_urls, ensure_ascii=False),
    )
    if (peek_idx is None or not peek_items) and not peek_urls:
        logger.info("ingest_noop no_file_parts_no_urls")
        return messages, [], None

    t0 = time.perf_counter()
    msgs = copy.deepcopy(messages)
    user_idx, indexed_items = extract_file_work_items(msgs)
    logger.info(
        "ingest_extract deepcopy_user_idx=%s indexed_parts=%s",
        user_idx,
        _file_items_summary(indexed_items) if indexed_items else "[]",
    )

    drop_indices: set[int] = set()
    tasks: list[Any] = []
    meta: list[tuple[str, int | str]] = []  # kind, key (part index for files, url for urls)

    if user_idx is not None:
        for part_idx, item in indexed_items:
            if item.mime == "application/pdf" or item.filename.lower().endswith(".pdf"):
                tasks.append(_process_one_pdf(item, settings))
                meta.append(("pdf", part_idx))
                drop_indices.add(part_idx)
            elif _is_audio_item(item.mime, item.filename):
                tasks.append(_process_one_audio(item, settings, http))
                meta.append(("audio", part_idx))
                drop_indices.add(part_idx)
            elif is_richdoc_item(item.mime, item.filename):
                tasks.append(_process_one_richdoc(item))
                meta.append(("richdoc", part_idx))
                drop_indices.add(part_idx)
            elif _is_plain_text_item(item.mime, item.filename):
                tasks.append(_process_one_plain_text(item))
                meta.append(("text", part_idx))
                drop_indices.add(part_idx)

    for url in peek_urls:
        tasks.append(_process_one_url(url, settings, http))
        meta.append(("url", url))

    if not tasks:
        logger.info(
            "ingest_no_tasks_after_queue user_idx=%s indexed_n=%s url_n=%s",
            user_idx,
            len(indexed_items),
            len(peek_urls),
        )
        return messages, [], None

    results = await asyncio.gather(*tasks, return_exceptions=True)
    artifacts: list[dict[str, Any]] = []
    for (kind, key), res in zip(meta, results, strict=True):
        if isinstance(res, Exception):
            logger.warning("ingest_task_failed kind=%s key=%s err=%s", kind, key, res)
            artifacts.append(
                {
                    "type": "ingest_error",
                    "title": str(key),
                    "content": str(res),
                }
            )
            continue
        artifacts.append(res)

    if user_idx is not None and drop_indices:
        strip_content_indices(msgs, user_idx, drop_indices)
    sys_msg = _build_artifact_system_message(artifacts)
    msgs.insert(0, sys_msg)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    trace_artifacts = [_artifact_for_trace(a) for a in artifacts]
    logger.info(
        "ingest_complete ms=%.2f artifacts=%s",
        elapsed_ms,
        json.dumps([a.get("type") for a in artifacts]),
    )
    return msgs, trace_artifacts, elapsed_ms
