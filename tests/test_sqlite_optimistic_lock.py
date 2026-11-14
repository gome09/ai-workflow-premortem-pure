# tests/test_sqlite_optimistic_lock.py
"""SQLite must fail closed on concurrent stale saves (no silent overwrite)."""

from __future__ import annotations

import pytest

from core.models import ProjectContext
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.errors import StaleContextError, TenantIsolationError


def _store(tmp_path) -> SQLiteSessionStore:
    store = SQLiteSessionStore(str(tmp_path / "optimistic.db"))
    store.initialize()
    return store


def test_stale_second_save_is_rejected(tmp_path):
    store = _store(tmp_path)
    ctx = ProjectContext(tenant_id="tenant-a")
    store.create(ctx)
    session_id = ctx.session_id

    first = store.load(session_id, "tenant-a")
    second = store.load(session_id, "tenant-a")
    assert first is not None and second is not None
    assert first._storage_version == 0
    assert second._storage_version == 0

    first.session_name = "first writer"
    store.save(first)

    second.session_name = "second writer"
    with pytest.raises(StaleContextError) as excinfo:
        store.save(second)

    assert excinfo.value.expected_version == 0
    assert excinfo.value.actual_version == 1

    reloaded = store.load(session_id, "tenant-a")
    assert reloaded is not None
    assert reloaded.session_name == "first writer"


def test_cross_tenant_overwrite_is_rejected(tmp_path):
    store = _store(tmp_path)
    ctx = ProjectContext(tenant_id="tenant-a")
    store.create(ctx)

    intruder = ProjectContext(session_id=ctx.session_id, tenant_id="tenant-b")
    intruder._storage_version = 0
    with pytest.raises(TenantIsolationError):
        store.save(intruder)


def test_new_session_starts_at_version_zero_and_increments(tmp_path):
    store = _store(tmp_path)
    ctx = ProjectContext(tenant_id="tenant-a")
    store.create(ctx)
    assert ctx._storage_version == 0

    ctx.session_name = "changed"
    store.save(ctx)
    assert ctx._storage_version == 1

    reloaded = store.load(ctx.session_id, "tenant-a")
    assert reloaded is not None
    assert reloaded._storage_version == 1
    assert reloaded.session_name == "changed"
