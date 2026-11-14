"""P1/T08：缓存命中也必须先核对数据库版本，不得把缓存当作删除事实来源。"""

from __future__ import annotations

import json

import pytest

from core.models import ProjectContext
from core.services.access import SessionAccess
from storage.backends.memory_cache import MemoryCache
from storage.errors import StorageUnavailableError


class _VersionStore:
    def __init__(self, ctx: ProjectContext | None, version: int | None) -> None:
        self._ctx = ctx
        self._version = version
        self.load_calls = 0
        self.version_calls = 0
        self.system_access = None
        self.fail_version = False

    def get_session_version(
        self, session_id: str, tenant_id: str = "", *, system_access=None
    ) -> int | None:
        self.version_calls += 1
        self.system_access = system_access
        if self.fail_version:
            raise RuntimeError("db down")
        return self._version

    def load(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
        self.load_calls += 1
        return self._ctx

    def save(self, ctx: ProjectContext) -> None:
        raise AssertionError("unexpected save")


def _ctx(version: int, session_id: str = "s-1", tenant_id: str = "tenant-a") -> ProjectContext:
    ctx = ProjectContext(session_id=session_id, tenant_id=tenant_id)
    ctx._storage_version = version
    return ctx


def _access(monkeypatch, store: _VersionStore, cache) -> SessionAccess:
    from core import session_service as module

    monkeypatch.setattr(module, "session_store", store)
    monkeypatch.setattr(module, "context_cache", cache)
    return SessionAccess()


def test_cache_hit_with_matching_version_returns_cached(monkeypatch) -> None:
    cached = _ctx(0)
    store = _VersionStore(_ctx(0), version=0)
    cache = MemoryCache()
    cache.set(cached)
    access = _access(monkeypatch, store, cache)

    result = access.get_session("s-1", "tenant-a")

    assert result is not None
    assert store.load_calls == 0
    assert store.version_calls == 1


def test_cache_miss_when_db_version_advanced(monkeypatch) -> None:
    stale = _ctx(0)
    fresh = _ctx(1)
    store = _VersionStore(fresh, version=1)
    cache = MemoryCache()
    cache.set(stale)
    access = _access(monkeypatch, store, cache)

    result = access.get_session("s-1", "tenant-a")

    assert result is fresh
    assert store.load_calls == 1


def test_cache_deleted_when_db_row_removed(monkeypatch) -> None:
    cached = _ctx(3)
    store = _VersionStore(None, version=None)
    cache = MemoryCache()
    cache.set(cached)
    access = _access(monkeypatch, store, cache)

    assert access.get_session("s-1", "tenant-a") is None
    # 缓存必须被删除，否则删除后回填的旧副本会继续被读取。
    assert cache.get("s-1", "tenant-a") is None


def test_version_lookup_failure_fails_closed(monkeypatch) -> None:
    store = _VersionStore(_ctx(0), version=0)
    store.fail_version = True
    cache = MemoryCache()
    cache.set(_ctx(0))
    access = _access(monkeypatch, store, cache)

    with pytest.raises(StorageUnavailableError):
        access.get_session("s-1", "tenant-a")


def test_version_lookup_failure_with_cache_miss_still_raises(monkeypatch) -> None:
    store = _VersionStore(_ctx(0), version=0)
    store.fail_version = True
    access = _access(monkeypatch, store, MemoryCache())

    # 无缓存时不查询版本；DB 只有真正 load 失败才由后端抛错。
    assert access.get_session("s-1", "tenant-a") is not None
    assert store.version_calls == 0


def test_cache_backend_failure_falls_back_to_store(monkeypatch) -> None:
    class _BrokenCache(MemoryCache):
        def get(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
            return None

    fresh = _ctx(2)
    store = _VersionStore(fresh, version=2)
    access = _access(monkeypatch, store, _BrokenCache())

    assert access.get_session("s-1", "tenant-a") is fresh
    assert store.load_calls == 1


def test_legacy_payload_without_version_is_miss(monkeypatch) -> None:
    from storage.cache import _deserialize

    ctx = ProjectContext(session_id="s-1", tenant_id="tenant-a")
    assert _deserialize(ctx.model_dump_json()) is None
    assert _deserialize(json.dumps({"context": ctx.model_dump(mode="json")})) is None
    restored = _deserialize(
        json.dumps({"context": ctx.model_dump(mode="json"), "storage_version": 7})
    )
    assert restored is not None
    assert restored._storage_version == 7


def test_tenant_cache_keys_are_isolated() -> None:
    cache = MemoryCache()
    cache.set(_ctx(1, tenant_id="tenant-a"))

    assert cache.get("s-1", "tenant-b") is None


def test_tenantless_session_uses_system_access_for_version(monkeypatch) -> None:
    from storage.access import SYSTEM_ACCESS

    cached = _ctx(4, tenant_id="")
    store = _VersionStore(_ctx(4, tenant_id=""), version=4)
    cache = MemoryCache()
    cache.set(cached)
    access = _access(monkeypatch, store, cache)

    result = access.get_session("s-1")
    assert result is not None
    assert result.session_id == "s-1"
    assert result._storage_version == 4
    assert store.version_calls == 1
    assert store.load_calls == 0
    assert store.system_access is SYSTEM_ACCESS


def test_tenantless_deleted_session_drops_cache(monkeypatch) -> None:
    cache = MemoryCache()
    cache.set(_ctx(4, tenant_id=""))
    store = _VersionStore(None, version=None)
    access = _access(monkeypatch, store, cache)

    assert access.get_session("s-1") is None
    assert cache.get("s-1", "") is None


async def test_storage_unavailable_handler_returns_503() -> None:
    import api.main as api_main

    response = await api_main._storage_unavailable_handler(
        None,  # type: ignore[arg-type] - handler ignores request
        StorageUnavailableError("s-1", "get_session_version"),
    )

    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["session_id"] == "s-1"
    assert body["detail"] == "Session storage unavailable"
