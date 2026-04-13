"""Log full incoming chat payloads (debug). No env toggles — always verbose."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

# Very large bodies are split across log lines (avoid single-line limits / OOM in log aggregators).
_CHUNK_CHARS = 120_000


def sanitize_for_log(
    obj: Any,
    *,
    content_str_clip: int = 16_000,
    url_len_threshold: int = 600,
    _depth: int = 0,
) -> Any:
    """Redact huge / binary URLs; clip very long strings (used in unit tests / optional tooling)."""
    if _depth > 24:
        return "<max_depth>"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        if obj.startswith("data:") or len(obj) > url_len_threshold:
            return f"<redacted str len={len(obj)}>"
        if len(obj) > content_str_clip:
            return obj[: content_str_clip - 24] + f"... <truncated {len(obj)} chars>"
        return obj
    if isinstance(obj, list):
        return [
            sanitize_for_log(x, content_str_clip=content_str_clip, url_len_threshold=url_len_threshold, _depth=_depth + 1)
            for x in obj
        ]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in ("url", "detail", "b64_json") and isinstance(v, str) and (
                v.startswith("data:") or len(v) > url_len_threshold
            ):
                out[k] = f"<redacted str len={len(v)}>"
            elif k == "image_url" and isinstance(v, dict):
                out[k] = sanitize_for_log(v, content_str_clip=content_str_clip, url_len_threshold=url_len_threshold, _depth=_depth + 1)
            else:
                out[k] = sanitize_for_log(v, content_str_clip=content_str_clip, url_len_threshold=url_len_threshold, _depth=_depth + 1)
        return out
    return str(obj)


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()[:16]


def _fingerprint_blob(s: str) -> dict[str, Any]:
    """Len + hash without hashing multi-MB strings whole."""
    if not isinstance(s, str):
        return {"kind": type(s).__name__}
    n = len(s)
    head = s[:65536]
    h = hashlib.sha256(f"{n}:{head}".encode("utf-8", errors="replace")).hexdigest()[:16]
    return {"len": n, "sha256_16": h}


def build_messages_digest(messages: Any) -> list[dict[str, Any]]:
    """Per-message summary: lengths + hashes for strings and multimodal parts (see docs/WEBUI_PAYLOAD.md)."""
    if not isinstance(messages, list):
        return [{"error": "messages_not_a_list", "type": type(messages).__name__}]

    out: list[dict[str, Any]] = []
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            out.append({"idx": i, "role": None, "error": "not_a_dict", "type": type(m).__name__})
            continue
        role = m.get("role")
        content = m.get("content")
        entry: dict[str, Any] = {"idx": i, "role": role}

        if isinstance(content, str):
            entry["content_kind"] = "str"
            entry["str_len"] = len(content)
            entry["str_sha256_16"] = _sha16(content) if content else ""
        elif isinstance(content, list):
            entry["content_kind"] = "parts"
            parts_out: list[dict[str, Any]] = []
            for j, p in enumerate(content):
                if not isinstance(p, dict):
                    parts_out.append({"part": j, "raw_type": type(p).__name__})
                    continue
                ptype = str(p.get("type") or "").lower()
                rec: dict[str, Any] = {"part": j, "type": ptype or "?"}
                if ptype == "text":
                    tx = p.get("text", "")
                    if isinstance(tx, str):
                        rec["text_len"] = len(tx)
                        rec["text_sha256_16"] = _sha16(tx) if tx else ""
                elif ptype == "image_url":
                    url = (p.get("image_url") or {}).get("url", "")
                    if isinstance(url, str):
                        rec.update(_fingerprint_blob(url))
                elif ptype == "file":
                    fobj = p.get("file") or {}
                    fd = fobj.get("file_data") if isinstance(fobj, dict) else None
                    if isinstance(fobj, dict):
                        rec["filename"] = fobj.get("filename")
                    if isinstance(fd, str):
                        rec["file_data"] = _fingerprint_blob(fd)
                elif ptype in ("input_audio", "audio"):
                    ia = p.get("input_audio")
                    if isinstance(ia, dict):
                        rec["filename"] = ia.get("filename")
                        rec["format"] = ia.get("format")
                        for key in ("data", "base64"):
                            v = ia.get(key)
                            if isinstance(v, str):
                                rec[key] = _fingerprint_blob(v)
                else:
                    rec["keys"] = sorted(p.keys())
                parts_out.append(rec)
            entry["parts"] = parts_out
        elif content is None:
            entry["content_kind"] = "null"
        else:
            entry["content_kind"] = type(content).__name__

        out.append(entry)
    return out


def _log_body_chunks(log: logging.Logger, prefix: str, raw: str) -> None:
    if len(raw) <= _CHUNK_CHARS:
        log.info("%s json=%s", prefix, raw)
        return
    n = (len(raw) + _CHUNK_CHARS - 1) // _CHUNK_CHARS
    log.info("%s total_json_len=%s json_parts=%s", prefix, len(raw), n)
    for part_i, start in enumerate(range(0, len(raw), _CHUNK_CHARS)):
        chunk = raw[start : start + _CHUNK_CHARS]
        log.info("%s json_part=%s/%s %s", prefix, part_i + 1, n, chunk)


def log_full_chat_completion_request(log: logging.Logger, phase: str, body: dict[str, Any]) -> None:
    """Log digest (hashes/lens) + full JSON body. Always on — for WebUI ↔ orchestrator debugging."""
    try:
        messages = body.get("messages")
        digest = build_messages_digest(messages)
        log.info("incoming_chat_digest phase=%s %s", phase, json.dumps(digest, ensure_ascii=False))

        extras = {k: body[k] for k in body if k != "messages"}
        if extras:
            log.info("incoming_chat_non_messages phase=%s %s", phase, json.dumps(extras, ensure_ascii=False, default=str))

        raw = json.dumps(body, ensure_ascii=False, default=str)
        _log_body_chunks(log, f"incoming_chat_full phase={phase}", raw)
    except Exception as e:  # noqa: BLE001
        log.warning("incoming_chat_full_log_failed phase=%s err=%s", phase, e)
