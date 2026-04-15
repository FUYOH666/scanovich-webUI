"""Push Open WebUI message status events (type=status) during orchestration."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any, Mapping

import httpx
from fastapi import Request

from gpthub_orchestrator.settings import Settings

logger = logging.getLogger("gpthub_orchestrator.webui_status")

# Defaults match open_webui/env.py; docs sometimes use hyphenated spellings.
_CHAT_HDR_NAMES = (
    "x-openwebui-chat-id",
    "x-open-webui-chat-id",
)
_MSG_HDR_NAMES = (
    "x-openwebui-message-id",
    "x-open-webui-message-id",
)


def _header_ci(headers: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    lower = {k.lower(): v for k, v in headers.items()}
    for n in names:
        v = lower.get(n.lower())
        if v:
            s = str(v).strip()
            if s:
                return s
    return None


def webui_chat_message_ids_from_request(request: Request) -> tuple[str | None, str | None]:
    h = request.headers
    chat = _header_ci(h, _CHAT_HDR_NAMES)
    msg = _header_ci(h, _MSG_HDR_NAMES)
    return chat, msg


async def emit_webui_message_status(
    http: httpx.AsyncClient,
    settings: Settings,
    *,
    chat_id: str,
    message_id: str,
    description: str,
    done: bool,
    extra: dict[str, Any] | None = None,
) -> None:
    base = (settings.orchestrator_webui_base_url or "").rstrip("/")
    secret = (settings.gpthub_internal_event_secret or "").strip()
    api_key = (settings.orchestrator_webui_event_api_key or "").strip()
    if not settings.orchestrator_webui_status_enabled or not base or (not secret and not api_key):
        return
    if secret:
        url = f"{base}/api/v1/internal/gpthub/chats/{chat_id}/messages/{message_id}/event"
        headers = {
            "X-GPTHub-Internal-Event-Secret": secret,
            "Content-Type": "application/json",
        }
    else:
        url = f"{base}/api/v1/chats/{chat_id}/messages/{message_id}/event"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data: dict[str, Any] = {"description": description, "done": done, "hidden": False}
    if extra:
        data.update(extra)
    try:
        r = await http.post(
            url,
            headers=headers,
            json={"type": "status", "data": data},
            timeout=10.0,
        )
        if r.status_code >= 400:
            logger.debug(
                "webui_status_post_failed status=%s chat_id=%s message_id=%s body=%s",
                r.status_code,
                chat_id,
                message_id,
                r.text[:300],
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("webui_status_post_error err=%s", e)


class WebuiStatusBridge:
    """Optional bridge when WebUI forwards chat/message headers and secret or API key is set."""

    def __init__(
        self,
        chat_id: str | None,
        message_id: str | None,
        http: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self.chat_id = chat_id
        self.message_id = message_id
        self.http = http
        self.settings = settings

    @classmethod
    def for_request(cls, request: Request, http: httpx.AsyncClient, settings: Settings) -> WebuiStatusBridge:
        c, m = webui_chat_message_ids_from_request(request)
        return cls(c, m, http, settings)

    def is_active(self) -> bool:
        if not self.settings.orchestrator_webui_status_enabled:
            return False
        if not (self.settings.orchestrator_webui_base_url or "").strip():
            return False
        secret = (self.settings.gpthub_internal_event_secret or "").strip()
        api_key = (self.settings.orchestrator_webui_event_api_key or "").strip()
        if not secret and not api_key:
            return False
        return bool(self.chat_id and self.message_id)

    async def working(self, description: str) -> None:
        if not self.is_active() or not self.chat_id or not self.message_id:
            return
        await emit_webui_message_status(
            self.http,
            self.settings,
            chat_id=self.chat_id,
            message_id=self.message_id,
            description=description,
            done=False,
        )

    async def council_phase(self, phase: str, experts_ready: int, experts_total: int) -> None:
        """Structured Expert Council progress for Open WebUI (action=gpthub_council)."""
        if not self.is_active() or not self.chat_id or not self.message_id:
            return
        if phase == "experts":
            desc = f"Эксперты: {experts_ready}/{experts_total}"
        elif phase == "synthesis":
            desc = "Суммаризатор объединяет ответы…"
        elif phase == "synthesis_fallback":
            desc = "Готовлю ответ (fallback)…"
        else:
            desc = "Expert Council…"
        await emit_webui_message_status(
            self.http,
            self.settings,
            chat_id=self.chat_id,
            message_id=self.message_id,
            description=desc,
            done=False,
            extra={
                "action": "gpthub_council",
                "phase": phase,
                "experts_ready": experts_ready,
                "experts_total": experts_total,
            },
        )

    async def pptx_slides_progress(self, slide_current: int, slide_total: int) -> None:
        """Structured PPTX build progress (action=gpthub_pptx)."""
        if not self.is_active() or not self.chat_id or not self.message_id:
            return
        desc = f"Слайдов готово: {slide_current}/{slide_total}"
        await emit_webui_message_status(
            self.http,
            self.settings,
            chat_id=self.chat_id,
            message_id=self.message_id,
            description=desc,
            done=False,
            extra={
                "action": "gpthub_pptx",
                "slide_current": slide_current,
                "slide_total": slide_total,
            },
        )

    async def complete(self, description: str = "Готово.") -> None:
        if not self.is_active() or not self.chat_id or not self.message_id:
            return
        await emit_webui_message_status(
            self.http,
            self.settings,
            chat_id=self.chat_id,
            message_id=self.message_id,
            description=description,
            done=True,
        )


async def wrap_async_sse_with_webui_complete(
    bridge: WebuiStatusBridge,
    gen: AsyncIterator[bytes],
    *,
    done_msg: str = "Готово.",
) -> AsyncIterator[bytes]:
    """Ensure complete() runs when the SSE generator is closed (success or error)."""
    try:
        async for chunk in gen:
            yield chunk
    finally:
        await bridge.complete(done_msg)


async def wrap_sync_sse_with_webui_complete(
    bridge: WebuiStatusBridge,
    gen: Iterator[bytes],
    *,
    done_msg: str = "Готово.",
) -> AsyncIterator[bytes]:
    """Async wrapper for *sync* byte iterators (short-circuit SSE helpers).

    Do not pass an async generator here: use ``async def`` + ``yield`` only with
    :func:`wrap_async_sse_with_webui_complete`.
    """
    try:
        for chunk in gen:
            yield chunk
    finally:
        await bridge.complete(done_msg)
