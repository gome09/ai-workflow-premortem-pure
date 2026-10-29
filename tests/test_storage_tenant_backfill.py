"""P3 回归：历史 NULL 租户会话的幂等回填（dry-run / apply / 租户校验）。"""

from __future__ import annotations

import pytest

from storage.backends.postgres import PostgresSessionStore


class _Result:
    def __init__(
        self,
        *,
        row: dict | None = None,
        rows: list[dict] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self) -> dict | None:
        return self._row

    def fetchall(self) -> list[dict]:
        return self._rows


class _BackfillConnection:
    """psycopg connection double；按语句类型返回租户校验、孤儿会话与更新行数。"""

    def __init__(
        self,
        *,
        tenant_exists: bool = True,
        orphan_ids: list[str] | None = None,
        update_counts: dict[str, int] | None = None,
    ) -> None:
        self.tenant_exists = tenant_exists
        self.orphan_ids = orphan_ids or []
        self.update_counts = update_counts or {}
        self.executed: list[tuple[str, tuple | None]] = []
        self.committed = False

    def execute(self, sql: str, params: tuple | None = None) -> _Result:
        normalized = " ".join(sql.split())
        self.executed.append((normalized, params))
        if normalized.upper().startswith("SELECT"):
            if "FROM tenants" in normalized:
                return _Result(row={"ok": 1} if self.tenant_exists else None)
            return _Result(rows=[{"session_id": sid} for sid in self.orphan_ids])
        for table, count in self.update_counts.items():
            if normalized.startswith(f"UPDATE {table}"):
                return _Result(rowcount=count)
        return _Result(rowcount=0)

    def commit(self) -> None:
        self.committed = True


class _ConnContext:
    def __init__(self, conn: _BackfillConnection) -> None:
        self._conn = conn

    def __enter__(self) -> _BackfillConnection:
        return self._conn

    def __exit__(self, *exc_info: object) -> bool:
        return False


def _store_with_conn(conn: _BackfillConnection) -> PostgresSessionStore:
    store = PostgresSessionStore()
    store._get_conn = lambda: _ConnContext(conn)  # type: ignore[method-assign]
    return store


def test_dry_run_reports_matches_without_writing() -> None:
    conn = _BackfillConnection(orphan_ids=["s-1", "s-2", "s-3"])
    store = _store_with_conn(conn)

    result = store.backfill_orphan_sessions("tenant-a")

    assert result == {
        "tenant_id": "tenant-a",
        "dry_run": True,
        "sessions_matched": 3,
        "sessions_updated": 0,
        "human_actions_updated": 0,
        "interrupt_resume_outbox_updated": 0,
        "gate_evaluation_records_updated": 0,
    }
    assert not any(sql.startswith("UPDATE") for sql, _ in conn.executed)
    assert conn.committed is False


def test_apply_updates_only_null_tenant_rows() -> None:
    conn = _BackfillConnection(
        orphan_ids=["s-1", "s-2"],
        update_counts={
            "sessions": 2,
            "human_actions": 5,
            "interrupt_resume_outbox": 1,
            "gate_evaluation_records": 4,
        },
    )
    store = _store_with_conn(conn)

    result = store.backfill_orphan_sessions("tenant-a", dry_run=False)

    updates = [sql for sql, _ in conn.executed if sql.startswith("UPDATE")]
    assert len(updates) == 4
    # 幂等保证：四条更新都只触碰 tenant_id IS NULL 的行。
    assert all("tenant_id IS NULL" in sql for sql in updates)
    assert updates[0].startswith("UPDATE sessions SET tenant_id = %s::uuid")
    assert conn.committed is True
    assert result["sessions_updated"] == 2
    assert result["human_actions_updated"] == 5
    assert result["interrupt_resume_outbox_updated"] == 1
    assert result["gate_evaluation_records_updated"] == 4


def test_apply_without_matches_skips_writes() -> None:
    conn = _BackfillConnection(orphan_ids=[])
    store = _store_with_conn(conn)

    result = store.backfill_orphan_sessions("tenant-a", dry_run=False)

    assert result["sessions_matched"] == 0
    assert result["sessions_updated"] == 0
    assert not any(sql.startswith("UPDATE") for sql, _ in conn.executed)
    assert conn.committed is False


def test_unknown_tenant_is_rejected_before_any_update() -> None:
    conn = _BackfillConnection(tenant_exists=False, orphan_ids=["s-1"])
    store = _store_with_conn(conn)

    with pytest.raises(ValueError, match="Tenant not found"):
        store.backfill_orphan_sessions("tenant-missing", dry_run=False)

    assert len(conn.executed) == 1
    assert conn.committed is False


def test_explicit_session_ids_scope_the_backfill() -> None:
    conn = _BackfillConnection(orphan_ids=["s-1"])
    store = _store_with_conn(conn)

    store.backfill_orphan_sessions("tenant-a", ["s-1", "s-2"], dry_run=False)

    select_sql, select_params = conn.executed[1]
    assert "session_id = ANY(%s)" in select_sql
    assert select_params == (["s-1", "s-2"],)

    update_params = next(
        params for sql, params in conn.executed if sql.startswith("UPDATE sessions")
    )
    # 更新只作用于实际匹配到的孤儿会话，与 sessions_matched 计数保持一致。
    assert update_params == ("tenant-a", ["s-1"])
