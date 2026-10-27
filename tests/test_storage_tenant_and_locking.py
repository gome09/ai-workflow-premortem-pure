"""Storage correctness: tenant isolation, optimistic locking, governance aggregation."""

from __future__ import annotations

import pytest

from core.models import PendingHumanAction, ProjectContext, SessionState
from storage.backends.postgres import (
    PostgresSessionStore,
    _aggregate_actions_backlog,
    _aggregate_governance_overview,
)
from storage.errors import StaleContextError, TenantIsolationError


class _FakeResult:
    def __init__(self, row: dict | None = None, rows: list[dict] | None = None) -> None:
        self._row = row
        self._rows = rows or []

    def fetchone(self) -> dict | None:
        return self._row

    def fetchall(self) -> list[dict]:
        return self._rows


class _FakeConnection:
    """Minimal psycopg connection double capturing executed statements."""

    def __init__(self, select_row: dict | None = None) -> None:
        self.select_row = select_row
        self.executed: list[tuple[str, tuple | None]] = []
        self.many: list[tuple[str, list[tuple]]] = []
        self.committed = False

    def execute(self, sql: str, params: tuple | None = None) -> _FakeResult:
        self.executed.append((" ".join(sql.split()), params))
        if sql.lstrip().upper().startswith("SELECT"):
            return _FakeResult(row=self.select_row)
        return _FakeResult()

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        self.many.append((" ".join(sql.split()), rows))

    def cursor(self) -> _FakeConnection:
        return self

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def commit(self) -> None:
        self.committed = True


def _store_with_conn(conn: _FakeConnection) -> PostgresSessionStore:
    store = PostgresSessionStore()
    store._get_conn = lambda: _FakeConnContext(conn)  # type: ignore[method-assign]
    return store


class _FakeConnContext:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    def __enter__(self) -> _FakeConnection:
        return self._conn

    def __exit__(self, *exc_info) -> bool:
        return False


def test_save_rejects_cross_tenant_overwrite() -> None:
    conn = _FakeConnection(select_row={"version": 3, "tenant_id": "tenant-b"})
    store = _store_with_conn(conn)
    ctx = ProjectContext(session_id="s-1", tenant_id="tenant-a")
    ctx._storage_version = 3

    with pytest.raises(TenantIsolationError):
        store.save(ctx)

    assert conn.committed is False
    assert not any("UPDATE sessions" in sql for sql, _ in conn.executed)


def test_save_rejects_stale_version() -> None:
    conn = _FakeConnection(select_row={"version": 5, "tenant_id": "tenant-a"})
    store = _store_with_conn(conn)
    ctx = ProjectContext(session_id="s-1", tenant_id="tenant-a")
    ctx._storage_version = 2

    with pytest.raises(StaleContextError) as excinfo:
        store.save(ctx)

    assert excinfo.value.expected_version == 2
    assert excinfo.value.actual_version == 5
    assert conn.committed is False


def test_save_increments_version_and_writes_it_back() -> None:
    conn = _FakeConnection(select_row={"version": 4, "tenant_id": "tenant-a"})
    store = _store_with_conn(conn)
    ctx = ProjectContext(session_id="s-1", tenant_id="tenant-a")
    ctx._storage_version = 4

    store.save(ctx)

    assert ctx._storage_version == 5
    assert any("version = version + 1" in sql for sql, _ in conn.executed)
    assert conn.committed is True


def test_save_insert_path_uses_version_zero() -> None:
    conn = _FakeConnection(select_row=None)
    store = _store_with_conn(conn)
    ctx = ProjectContext(session_id="s-new", tenant_id="tenant-a", current_state=SessionState.INIT)

    store.save(ctx)

    assert ctx._storage_version == 0
    insert_sql, _ = next(
        (sql, params) for sql, params in conn.executed if sql.startswith("INSERT INTO sessions")
    )
    assert "version" in insert_sql
    assert ") VALUES (%s, %s::uuid, %s, %s, %s, %s, 0)" in insert_sql


def test_human_actions_sync_writes_tenant_id() -> None:
    conn = _FakeConnection()
    store = _store_with_conn(conn)
    ctx = ProjectContext(session_id="s-1", tenant_id="tenant-a")
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            action_type="approve",
            title="t",
            description="d",
        )
    )

    store._sync_human_actions(conn, ctx)

    assert len(conn.many) == 1
    insert_sql, rows = conn.many[0]
    assert "tenant_id" in insert_sql
    assert rows[0][2] == "tenant-a"


def test_postgres_load_requires_tenant_without_system_channel() -> None:
    conn = _FakeConnection()
    store = _store_with_conn(conn)

    with pytest.raises(TenantIsolationError):
        store.load("s-1")
    assert conn.executed == []


def test_postgres_list_and_delete_require_tenant() -> None:
    conn = _FakeConnection()
    store = _store_with_conn(conn)

    with pytest.raises(TenantIsolationError):
        store.list_sessions(limit=5)
    with pytest.raises(TenantIsolationError):
        store.delete("s-1")
    assert conn.executed == []


def test_governance_overview_structure_is_stable() -> None:
    overview = _aggregate_governance_overview(
        state_rows=[{"current_state": "init", "n": 2}, {"current_state": "stage_1", "n": 1}],
        eval_rows=[
            {"session_id": "a", "risk_tier": "high", "evaluated_at": 1},
            {"session_id": "a", "risk_tier": "low", "evaluated_at": 2},
            {"session_id": "b", "risk_tier": "medium", "evaluated_at": 1},
        ],
        counts={
            "open_safety_findings": 4,
            "pending_actions": 2,
            "reports_exported": 1,
        },
    )

    assert overview == {
        "sessions_total": 3,
        "state_distribution": {"init": 2, "stage_1": 1},
        "risk_tier_distribution": {"low": 1, "medium": 1},
        "open_safety_findings": 4,
        "pending_actions": 2,
        "reports_exported": 1,
    }


def test_actions_backlog_orders_by_risk_and_limit() -> None:
    rows = [
        {
            "session_id": "a",
            "action_id": "a1",
            "title": "low action",
            "risk_level": "low",
            "stage_id": 1,
            "created_at": "2026-01-01T00:00:00",
        },
        {
            "session_id": "b",
            "action_id": "b1",
            "title": "critical action",
            "risk_level": "critical",
            "stage_id": 2,
            "created_at": "2026-01-02T00:00:00",
        },
    ]

    backlog = _aggregate_actions_backlog(rows, limit=1)

    assert len(backlog) == 1
    assert backlog[0]["action_id"] == "b1"
    assert backlog[0]["risk_level"] == "critical"
