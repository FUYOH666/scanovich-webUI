"""In-memory one-time PPTX artifact store for GET /artifacts/pptx/{id}?token=."""

from __future__ import annotations

import logging
import secrets
import threading
import time
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _Record:
    blob: bytes
    token: str
    expires_at: float
    filename: str


class PptxArtifactStore:
    """Single-use token: after successful GET the record is removed."""

    def __init__(self, *, ttl_seconds: float = 3600.0) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._by_id: dict[str, _Record] = {}

    def _purge_unlocked(self, now: float) -> None:
        dead = [k for k, r in self._by_id.items() if r.expires_at <= now]
        for k in dead:
            del self._by_id[k]

    def create(self, blob: bytes, *, filename: str = "presentation.pptx") -> tuple[str, str]:
        """Return (artifact_id, plaintext_token)."""
        now = time.monotonic()
        aid = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        fn = filename.strip() or "presentation.pptx"
        if not fn.lower().endswith(".pptx"):
            fn = f"{fn}.pptx"
        with self._lock:
            self._purge_unlocked(now)
            self._by_id[aid] = _Record(
                blob=blob,
                token=token,
                expires_at=now + self._ttl,
                filename=fn,
            )
        return aid, token

    def consume(self, artifact_id: str, token: str) -> tuple[bytes, str] | None:
        """Validate token, return (blob, filename) once, delete record."""
        now = time.monotonic()
        with self._lock:
            self._purge_unlocked(now)
            rec = self._by_id.get(artifact_id)
            if rec is None:
                logger.info("pptx_artifact_miss id=%s", artifact_id[:12])
                return None
            if rec.expires_at <= now:
                del self._by_id[artifact_id]
                logger.info("pptx_artifact_expired id=%s", artifact_id[:12])
                return None
            if not secrets.compare_digest(rec.token, token):
                logger.info("pptx_artifact_bad_token id=%s", artifact_id[:12])
                return None
            del self._by_id[artifact_id]
            return rec.blob, rec.filename


# Process-wide store (single uvicorn worker; multi-worker would need Redis etc.)
_store: PptxArtifactStore | None = None


def get_pptx_artifact_store(ttl_seconds: float) -> PptxArtifactStore:
    global _store
    if _store is None:
        _store = PptxArtifactStore(ttl_seconds=ttl_seconds)
    return _store


def reset_pptx_artifact_store_for_tests() -> None:
    global _store
    _store = None
