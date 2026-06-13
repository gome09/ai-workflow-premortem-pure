# storage/cache.py
"""
Factory wrapper — selects the correct cache backend based on STORAGE_BACKEND env var.

Callers continue to use:
    from storage.cache import context_cache

SQLite / lite mode → MemoryCache (in-process dict, no Redis)
Postgres mode      → ContextCache (Redis-backed, existing behaviour)

NOTE: `redis` is imported at module level so that existing tests can patch
      `storage.cache.redis.from_url` without modification.
"""

from __future__ import annotations

import logging

import redis

from core.config import settings
from core.models import ProjectContext

logger = logging.getLogger(__name__)

CONTEXT_TTL = settings.session_ttl_hours * 3600


class ContextCache:
    """
    Redis 热上下文缓存。
    cache key 格式：session:ctx:{tenant_id}:{session_id}，实现 tenant 级隔离。
    """

    def __init__(self):
        self._client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )

    def _key(self, session_id: str, tenant_id: str = "") -> str:
        return f"session:ctx:{tenant_id}:{session_id}"

    def set(self, ctx: ProjectContext) -> None:
        try:
            self._client.setex(
                self._key(ctx.session_id, ctx.tenant_id),
                CONTEXT_TTL,
                ctx.model_dump_json(),
            )
        except redis.RedisError as e:
            logger.warning(f"Redis set failed, degrading to PG-only: {e}")

    def get(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
        try:
            raw = self._client.get(self._key(session_id, tenant_id))
            if not raw:
                return None
            return ProjectContext.model_validate_json(raw)
        except redis.RedisError as e:
            logger.warning(f"Redis get failed: {e}")
            return None

    def delete(self, session_id: str, tenant_id: str = "") -> None:
        try:
            self._client.delete(self._key(session_id, tenant_id))
        except redis.RedisError as e:
            logger.warning(f"Redis delete failed: {e}")

    def refresh_ttl(self, session_id: str, tenant_id: str = "") -> None:
        try:
            self._client.expire(self._key(session_id, tenant_id), CONTEXT_TTL)
        except redis.RedisError as e:
            logger.warning(f"Redis expire failed: {e}")


def _make_cache():
    if settings.storage_backend == "sqlite":
        from storage.backends.memory_cache import MemoryCache

        return MemoryCache(ttl_seconds=CONTEXT_TTL)
    return ContextCache()


# Global singleton — identical public API regardless of backend
context_cache = _make_cache()
