"""Tests for Open WebUI message.files ingest via shared volume paths."""

from __future__ import annotations

import httpx
import pytest

from gpthub_orchestrator.ingest.open_webui_uploads import extract_open_webui_upload_work_items
from gpthub_orchestrator.ingest.pipeline import run_ingest_pipeline
from gpthub_orchestrator.settings import Settings


def _mk_settings(**kwargs: object) -> Settings:
    base = {
        "litellm_base_url": "http://litellm:4000",
        "orchestrator_api_key": "test",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_extract_open_webui_upload_work_items_reads_file(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    disk_file = uploads / "b9a42859_test.pptx"
    disk_file.write_bytes(b"pptx-bytes-here")

    msg = {
        "role": "user",
        "content": "",
        "files": [
            {
                "type": "file",
                "file": {
                    "path": "/app/backend/data/uploads/b9a42859_test.pptx",
                    "filename": "test.pptx",
                    "meta": {
                        "content_type": (
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        ),
                    },
                },
            }
        ],
    }
    settings = _mk_settings(
        orchestrator_open_webui_data_mount=str(tmp_path),
        orchestrator_open_webui_path_prefix="/app/backend/data",
    )
    items = extract_open_webui_upload_work_items(msg, settings)
    assert len(items) == 1
    assert items[0].filename == "test.pptx"
    assert items[0].raw == b"pptx-bytes-here"
    assert "presentationml" in items[0].mime


def test_extract_skips_path_traversal(tmp_path):
    settings = _mk_settings(
        orchestrator_open_webui_data_mount=str(tmp_path),
    )
    msg = {
        "role": "user",
        "files": [
            {
                "type": "file",
                "file": {
                    "path": "/app/backend/data/uploads/../../../etc/passwd",
                    "filename": "x",
                    "meta": {"content_type": "text/plain"},
                },
            }
        ],
    }
    assert extract_open_webui_upload_work_items(msg, settings) == []


@pytest.mark.asyncio
async def test_pipeline_ingests_open_webui_files_field(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "notes.txt").write_bytes(b"hello from shared volume")

    messages = [
        {
            "role": "user",
            "content": "",
            "files": [
                {
                    "type": "file",
                    "file": {
                        "path": "/app/backend/data/uploads/notes.txt",
                        "filename": "notes.txt",
                        "meta": {"content_type": "text/plain"},
                    },
                }
            ],
        }
    ]
    settings = _mk_settings(
        orchestrator_open_webui_data_mount=str(tmp_path),
    )
    async with httpx.AsyncClient() as http:
        new_msgs, artifacts, ms = await run_ingest_pipeline(messages, settings, http)
    assert ms is not None
    assert "files" not in new_msgs[-1]
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "document_text"
    assert "hello from shared volume" in artifacts[0]["content"]
    assert new_msgs[0]["role"] == "system"
