"""T05: retention purge rechecks the cutoff under the write transaction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.config import settings
from core.models import ProjectContext
from core.retention_service import run_retention_cycle
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

TENANT = "tenant-a"


@pytest.fixture
def store(tmp_path) -> SQLiteSessionStore:
    backend = SQLiteSessionStore(str(tmp_path / "retention-cutoff.db"))
    backend.initialize()
    return backend


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(tzinfo=None).isoformat()


def _backdate(store: SQLiteSessionStore, session_id: str, when: datetime) -> None:
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id=?",
            (_stamp(when), session_id),
        )
        conn.commit()


def _new_session(store: SQLiteSessionStore) -> ProjectContext:
    ctx = ProjectContext(tenant_id=TENANT, session_name="retention")
    store.create(ctx)
    return ctx


def _enable(monkeypatch, *, cutoff_days: int = 30) -> None:
    monkeypatch.setattr(settings, "session_retention_days", cutoff_days)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", False)
    monkeypatch.setattr(settings, "retention_batch_size", 100)


def _archive_count(store: SQLiteSessionStore, session_id: str) -> int:
    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_events_archive WHERE original_session_id=?",
            (session_id,),
        ).fetchone()
    return int(row["n"])


def test_candidate_updated_after_selection_is_skipped(store, monkeypatch) -> None:
    now = datetime(2026, 11, 13, tzinfo=UTC)
    ctx = _new_session(store)
    _backdate(store, ctx.session_id, now - timedelta(days=400))
    _enable(monkeypatch)
    cache = MemoryCache(ttl_seconds=3600)
    cache.set(ctx)

    candidate = {
        "session_id": ctx.session_id,
        "tenant_id": TENANT,
        "current_state": "complete",
        "created_at": ctx.created_at.isoformat(),
        "updated_at": (now - timedelta(days=400)).isoformat(),
    }
    monkeypatch.setattr(store, "count_expired_sessions", lambda cutoff: 1)
    monkeypatch.setattr(store, "list_expired_sessions", lambda cutoff, limit=1000: [candidate])

    # 模拟候选选出后用户成功更新：直接刷新 updated_at。
    _backdate(store, ctx.session_id, now - timedelta(days=1))

    result = run_retention_cycle(now=now, store=store, cache=cache)

    assert result["sessions_matched"] == 1
    assert result["sessions_purged"] == 0
    assert result["sessions_skipped"] == 1
    assert store.load(ctx.session_id, TENANT) is not None
    assert _archive_count(store, ctx.session_id) == 0
    assert cache.get(ctx.session_id, TENANT) is not None


def test_cutoff_boundary_is_strict(store, monkeypatch) -> None:
    now = datetime(2026, 11, 13, tzinfo=UTC)
    cutoff = now - timedelta(days=30)
    boundary = _new_session(store)
    _backdate(store, boundary.session_id, cutoff)
    older = _new_session(store)
    _backdate(store, older.session_id, cutoff - timedelta(seconds=1))
    _enable(monkeypatch)

    result = run_retention_cycle(now=now, store=store, cache=MemoryCache())

    assert result["sessions_purged"] == 1
    assert store.load(boundary.session_id, TENANT) is not None
    assert store.load(older.session_id, TENANT) is None


def test_second_cleaner_sees_not_found(store, monkeypatch) -> None:
    now = datetime(2026, 11, 13, tzinfo=UTC)
    ctx = _new_session(store)
    _backdate(store, ctx.session_id, now - timedelta(days=400))
    _enable(monkeypatch)

    first = store.purge_session(
        ctx.session_id, TENANT, "retention", {}, retention_cutoff=now - timedelta(days=30)
    )
    second = store.purge_session(
        ctx.session_id, TENANT, "retention", {}, retention_cutoff=now - timedelta(days=30)
    )

    assert first.deleted is True
    assert second.deleted is False
    assert second.reason == "not_found"


def test_archive_failure_rolls_back_and_keeps_session(store, monkeypatch) -> None:
    ctx = _new_session(store)

    def explode(summary):
        raise RuntimeError("archive failure")

    monkeypatch.setattr("storage.backends.sqlite_store.sanitize_purge_summary", explode)

    with pytest.raises(RuntimeError, match="archive failure"):
        store.purge_session(ctx.session_id, TENANT, "admin", {})

    assert store.load(ctx.session_id, TENANT) is not None
    assert _archive_count(store, ctx.session_id) == 0


def test_empty_tenant_requires_system_access(store) -> None:
    ctx = _new_session(store)

    with pytest.raises(Exception):
        store.purge_session(ctx.session_id, "", "retention", {})

    from storage.access import SYSTEM_ACCESS

    outcome = store.purge_session(ctx.session_id, "", "retention", {}, system_access=SYSTEM_ACCESS)
    assert outcome.deleted is False
    assert outcome.reason == "not_found"
