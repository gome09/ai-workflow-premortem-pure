"""T01: explicit create/save semantics for session parent rows."""

from __future__ import annotations

import pytest

from core.models import ProjectContext
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.errors import (
    SessionAlreadyExistsError,
    SessionNotFoundError,
    StaleContextError,
    TenantIsolationError,
)

TENANT = "tenant-a"


@pytest.fixture
def store(tmp_path) -> SQLiteSessionStore:
    backend = SQLiteSessionStore(str(tmp_path / "create.db"))
    backend.initialize()
    return backend


def _row_count(store: SQLiteSessionStore, table: str, session_id: str) -> int:
    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE session_id=?",  # noqa: S608
            (session_id,),
        ).fetchone()
    return int(row["n"])


def test_create_then_save_increments_version(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    store.create(ctx)
    assert ctx._storage_version == 0

    ctx.session_name = "renamed"
    store.save(ctx)
    assert ctx._storage_version == 1

    reloaded = store.load(ctx.session_id, TENANT)
    assert reloaded is not None
    assert reloaded.session_name == "renamed"


def test_save_never_recreates_deleted_context(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    ctx.pending_actions = []
    ctx.eval_cases = []
    store.create(ctx)
    loaded = store.load(ctx.session_id, TENANT)
    assert loaded is not None

    outcome = store.purge_session(ctx.session_id, TENANT, "admin", {"session_id": ctx.session_id})
    assert outcome.deleted is True

    loaded.session_name = "resurrect"
    with pytest.raises(SessionNotFoundError):
        store.save(loaded)

    assert _row_count(store, "sessions", ctx.session_id) == 0
    assert _row_count(store, "human_actions", ctx.session_id) == 0


def test_save_on_missing_row_does_not_insert(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    with pytest.raises(SessionNotFoundError):
        store.save(ctx)
    assert _row_count(store, "sessions", ctx.session_id) == 0


def test_duplicate_create_is_rejected_without_overwrite(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT, session_name="original")
    store.create(ctx)

    duplicate = ProjectContext(session_id=ctx.session_id, tenant_id=TENANT, session_name="other")
    with pytest.raises(SessionAlreadyExistsError):
        store.create(duplicate)

    reloaded = store.load(ctx.session_id, TENANT)
    assert reloaded is not None
    assert reloaded.session_name == "original"


def test_save_keeps_tenant_and_version_guards(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    store.create(ctx)

    intruder = ProjectContext(session_id=ctx.session_id, tenant_id="tenant-b")
    with pytest.raises(TenantIsolationError):
        store.save(intruder)

    first = store.load(ctx.session_id, TENANT)
    second = store.load(ctx.session_id, TENANT)
    assert first is not None and second is not None
    first.session_name = "first"
    store.save(first)
    second.session_name = "second"
    with pytest.raises(StaleContextError):
        store.save(second)


def test_cache_round_trip_preserves_storage_version(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    store.create(ctx)
    ctx.session_name = "cached"
    store.save(ctx)

    cache = MemoryCache(ttl_seconds=3600)
    cache.set(ctx)
    cached = cache.get(ctx.session_id, TENANT)
    assert cached is not None
    assert cached._storage_version == 1

    cached.session_name = "from-cache"
    store.save(cached)
    assert cached._storage_version == 2


async def test_session_not_found_handler_returns_409_and_clears_cache(monkeypatch) -> None:
    from starlette.requests import Request

    from api import main as api_main
    from auth.jwt import create_access_token

    class _Cache:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, str]] = []

        def delete(self, session_id: str, tenant_id: str = "") -> None:
            self.deleted.append((session_id, tenant_id))

    cache = _Cache()
    monkeypatch.setattr(api_main, "context_cache", cache)
    token = create_access_token({"sub": "u-1", "tenant_id": TENANT, "role": "admin"})
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/chat/s-1",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )

    response = await api_main._session_not_found_handler(request, SessionNotFoundError("s-1"))

    assert response.status_code == 409
    assert cache.deleted == [("s-1", TENANT)]
