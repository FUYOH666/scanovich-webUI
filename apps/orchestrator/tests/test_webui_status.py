"""Tests for Open WebUI status bridge header parsing."""

from unittest.mock import MagicMock

from gpthub_orchestrator.webui_status import webui_chat_message_ids_from_request


def test_webui_headers_default_names() -> None:
    req = MagicMock()
    req.headers = {
        "X-OpenWebUI-Chat-Id": "chat-1",
        "X-OpenWebUI-Message-Id": "msg-2",
    }
    c, m = webui_chat_message_ids_from_request(req)
    assert c == "chat-1"
    assert m == "msg-2"


def test_webui_headers_doc_style_hyphenated() -> None:
    req = MagicMock()
    req.headers = {
        "X-Open-WebUI-Chat-Id": "c",
        "X-Open-WebUI-Message-Id": "m",
    }
    c, m = webui_chat_message_ids_from_request(req)
    assert c == "c"
    assert m == "m"


def test_webui_headers_case_insensitive() -> None:
    req = MagicMock()
    req.headers = {
        "x-openwebui-chat-id": "C",
        "x-openwebui-message-id": "M",
    }
    c, m = webui_chat_message_ids_from_request(req)
    assert c == "C"
    assert m == "M"
