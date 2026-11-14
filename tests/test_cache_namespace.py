"""Cache namespace v2 and legacy-key separation."""

from __future__ import annotations

from core.models import ProjectContext
from storage.backends.memory_cache import MemoryCache
from storage.cache import ContextCache
from storage.cache_keys import CACHE_KEY_PREFIX, LEGACY_CACHE_KEY_PREFIX, context_cache_key


def test_key_helpers_use_versioned_prefix() -> None:
    key = context_cache_key("s-1", "tenant-a")
    assert key == f"{CACHE_KEY_PREFIX}:tenant-a:s-1"
    assert key.startswith("session:ctx:v2:")
    assert not key.startswith(f"{LEGACY_CACHE_KEY_PREFIX}tenant-a:s-1")


def test_redis_cache_key_uses_v2_namespace() -> None:
    cache = ContextCache.__new__(ContextCache)
    assert cache._key("s-1", "tenant-a") == "session:ctx:v2:tenant-a:s-1"


def test_memory_cache_uses_v2_namespace_and_ignores_legacy_keys() -> None:
    cache = MemoryCache(ttl_seconds=3600)
    ctx = ProjectContext(session_id="s-1", tenant_id="tenant-a")
    cache.set(ctx)

    assert cache.get("s-1", "tenant-a") is not None
    assert cache._store.get("session:ctx:v2:tenant-a:s-1") is not None  # noqa: SLF001
    assert cache._store.get("session:ctx:tenant-a:s-1") is None  # noqa: SLF001
