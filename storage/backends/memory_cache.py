# storage/backends/memory_cache.py
"""In-process dictionary cache — no Redis required (SQLite / lite mode)."""

from __future__ import annotations

import logging
import threading
import time

from core.models import ProjectContext

logger = logging.getLogger(__name__)


class MemoryCache:
    """
    In-process hot-context cache backed by a dict + threading.Lock.

    Implements approximate TTL: each entry stores its insertion timestamp.
    On get(), entries older than `ttl_seconds` are treated as expired.
    """

    def __init__(self, ttl_seconds: int = 72 * 3600):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[str, float]] = {}  # key -> (json_str, insert_time)
        self._lock = threading.Lock()

    def _key(self, session_id: str, tenant_id: str = "") -> str:
        return f"session:ctx:{tenant_id}:{session_id}"

    def set(self, ctx: ProjectContext) -> None:
        try:
            key = self._key(ctx.session_id, ctx.tenant_id or "")
            value = ctx.model_dump_json()
            with self._lock:
                self._store[key] = (value, time.monotonic())
        except Exception as e:  # noqa: BLE001
            logger.warning("MemoryCache set failed: %s", e)

    def get(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
        try:
            key = self._key(session_id, tenant_id)
            with self._lock:
                entry = self._store.get(key)
            if entry is None:
                return None
            value, insert_time = entry
            if time.monotonic() - insert_time > self._ttl:
                with self._lock:
                    self._store.pop(key, None)
                return None
            return ProjectContext.model_validate_json(value)
        except Exception as e:  # noqa: BLE001
            logger.warning("MemoryCache get failed: %s", e)
            return None

    def delete(self, session_id: str, tenant_id: str = "") -> None:
        try:
            key = self._key(session_id, tenant_id)
            with self._lock:
                self._store.pop(key, None)
        except Exception as e:  # noqa: BLE001
            logger.warning("MemoryCache delete failed: %s", e)

    def refresh_ttl(self, session_id: str, tenant_id: str = "") -> None:
        try:
            key = self._key(session_id, tenant_id)
            with self._lock:
                entry = self._store.get(key)
                if entry is not None:
                    self._store[key] = (entry[0], time.monotonic())
        except Exception as e:  # noqa: BLE001
            logger.warning("MemoryCache refresh_ttl failed: %s", e)
