"""Optional session date/time injected into the LLM system message (per request)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)


def build_session_clock_block(settings: Settings) -> tuple[str | None, str | None]:
    """
    Return (prefix_text_for_system_message, iso_timestamp_for_trace) or (None, None) if disabled.
    """
    if not settings.inject_request_datetime:
        return None, None

    tz_name = (settings.orchestrator_clock_tz or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("orchestrator_clock_tz_invalid tz=%s falling_back_to_UTC", tz_name)
        tz = timezone.utc
        tz_name = "UTC"

    now = datetime.now(tz)
    iso = now.isoformat()
    wall = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    prefix = (
        "[Session context: current date and time for this request]\n"
        f"- Wall clock (IANA timezone {tz_name}): {wall}\n"
        f"- ISO-8601: {iso}\n"
        "Use this when the user asks for \"today\", \"now\", or the current date/time. "
        "For other timezones, convert or ask the user which timezone they mean."
    )
    return prefix, iso
