"""Load Open WebUI chat attachments from a volume shared with the WebUI container."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from gpthub_orchestrator.ingest.parts import FileWorkItem
from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)


def extract_open_webui_upload_work_items(
    msg: dict[str, Any],
    settings: Settings,
) -> list[FileWorkItem]:
    """Build FileWorkItem list from message['files'] using on-disk paths under the shared mount."""
    mount = settings.orchestrator_open_webui_data_mount
    if not mount or not str(mount).strip():
        return []

    root = Path(mount).expanduser().resolve()
    if not root.is_dir():
        logger.warning("open_webui_upload_mount_missing path=%s", root)
        return []

    prefix = settings.orchestrator_open_webui_path_prefix.strip().rstrip("/")
    raw_files = msg.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        return []

    items: list[FileWorkItem] = []
    max_bytes = settings.ingest_fetch_max_bytes

    for entry in raw_files:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("file")
        if not isinstance(inner, dict):
            inner = entry
        path_str = inner.get("path")
        if not isinstance(path_str, str) or not path_str.strip():
            continue
        path_str = path_str.strip()
        if not path_str.startswith(prefix):
            logger.warning(
                "open_webui_upload_skip_unexpected_prefix path=%s expected_prefix=%s",
                path_str[:160],
                prefix,
            )
            continue
        rel = path_str[len(prefix) :].lstrip("/")
        if not rel:
            continue
        if ".." in Path(rel).parts:
            logger.warning("open_webui_upload_skip_unsafe_rel rel=%s", rel)
            continue

        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            logger.warning(
                "open_webui_upload_skip_traversal candidate=%s root=%s",
                candidate,
                root,
            )
            continue
        if not candidate.is_file():
            logger.warning("open_webui_upload_skip_not_file path=%s", candidate)
            continue

        try:
            sz = candidate.stat().st_size
        except OSError as e:
            logger.warning("open_webui_upload_stat_failed path=%s err=%s", candidate, e)
            continue
        if sz > max_bytes:
            logger.warning(
                "open_webui_upload_skip_too_large path=%s size=%s max=%s",
                candidate,
                sz,
                max_bytes,
            )
            continue

        filename = str(inner.get("filename") or "").strip() or candidate.name
        meta = inner.get("meta")
        mime = "application/octet-stream"
        if isinstance(meta, dict):
            ct = meta.get("content_type")
            if isinstance(ct, str) and ct.strip():
                mime = ct.strip().lower()

        try:
            raw = candidate.read_bytes()
        except OSError as e:
            logger.warning("open_webui_upload_read_failed path=%s err=%s", candidate, e)
            continue

        items.append(FileWorkItem(filename=filename, mime=mime, raw=raw))
        logger.info(
            "open_webui_upload_queued path=%s filename=%s mime=%s bytes=%s",
            candidate,
            filename,
            mime,
            len(raw),
        )

    return items
