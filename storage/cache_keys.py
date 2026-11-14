"""Versioned cache-key helpers shared by Redis and in-memory caches."""

from __future__ import annotations

# v2 起缓存键带版本前缀；旧键只在排空旧 worker 后由运维脚本清理。
CACHE_KEY_PREFIX = "session:ctx:v2"
LEGACY_CACHE_KEY_PREFIX = "session:ctx:"


def context_cache_key(session_id: str, tenant_id: str = "") -> str:
    return f"{CACHE_KEY_PREFIX}:{tenant_id}:{session_id}"
