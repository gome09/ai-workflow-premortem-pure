"""T1.6 留存执行器回归：dry-run、会话生命周期清理、审计留存与批次上限。"""

from __future__ import annotations

import gc
import json
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.audit_service import append_audit_event
from core.config import settings
from core.models import ProjectContext
from core.retention_service import run_retention_cycle
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


@pytest.fixture
def store(tmp_path):
    backend = SQLiteSessionStore(db_path=str(tmp_path / "retention.db"))
    backend.initialize()
    return backend


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(tzinfo=None).isoformat()


def _backdate_session(store, session_id: str, when: datetime) -> None:
    with store._get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (_stamp(when), session_id),
        )
        conn.commit()


def _insert_gate_eval(store, session_id: str, tenant_id: str) -> None:
    with store._get_conn() as conn:
        conn.execute(
            "INSERT INTO gate_evaluation_records "
            "(record_id, session_id, tenant_id, stage_id, risk_tier, passed, "
            " blocking_rule_ids, rule_versions, evaluated_at) "
            "VALUES (?, ?, ?, 1, 'low', 1, '[]', '{}', ?)",
            (str(uuid.uuid4()), session_id, tenant_id, datetime.utcnow().isoformat()),
        )
        conn.commit()


def _create_session(store, tenant_id: str = "tenant-a") -> ProjectContext:
    ctx = ProjectContext(tenant_id=tenant_id, session_name="retention-test")
    store.save(ctx)
    return ctx


def test_dry_run_reports_candidates_without_deleting(store, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    old = _create_session(store)
    _backdate_session(store, old.session_id, now - timedelta(days=400))
    cache = MemoryCache()

    monkeypatch.setattr(settings, "session_retention_days", 30)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", True)

    result = run_retention_cycle(now=now, store=store, cache=cache)

    assert result["dry_run"] is True
    assert result["sessions_matched"] == 1
    assert result["sessions_purged"] == 0
    assert store.load(old.session_id, "tenant-a") is not None


def test_apply_purges_session_and_gate_records(store, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    ctx = _create_session(store)
    _backdate_session(store, ctx.session_id, now - timedelta(days=400))
    _insert_gate_eval(store, ctx.session_id, "tenant-a")
    cache = MemoryCache()
    cache.set(ctx)

    monkeypatch.setattr(settings, "session_retention_days", 30)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", False)

    result = run_retention_cycle(now=now, store=store, cache=cache)

    assert result["sessions_matched"] == 1
    assert result["sessions_purged"] == 1
    assert store.load(ctx.session_id, "tenant-a") is None
    with store._get_conn() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM gate_evaluation_records WHERE session_id = ?",
            (ctx.session_id,),
        ).fetchone()
    assert remaining["n"] == 0
    assert cache.get(ctx.session_id, "tenant-a") is None


def test_audit_retention_deletes_expired_live_and_archived_rows(store, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    ctx = _create_session(store)
    append_audit_event(
        ctx,
        actor="system",
        event_type="retention_test",
        target_type="session",
        target_id=ctx.session_id,
    )
    store.save(ctx)

    with store._get_conn() as conn:
        conn.execute(
            "UPDATE audit_events SET created_at = ? WHERE session_id = ?",
            (_stamp(now - timedelta(days=400)), ctx.session_id),
        )
        conn.execute(
            "INSERT INTO audit_events_archive "
            "(archive_id, original_session_id, event_id, actor, event_type, target_type, "
            " target_id, before_snapshot, after_snapshot, metadata, original_created_at, archived_at) "
            "VALUES (?, ?, ?, 'system', 'retention_test', 'session', ?, NULL, NULL, ?, ?, ?)",
            (
                "arch-old",
                ctx.session_id,
                "evt-old",
                ctx.session_id,
                json.dumps({}),
                _stamp(now - timedelta(days=400)),
                _stamp(now),
            ),
        )
        conn.commit()

    monkeypatch.setattr(settings, "session_retention_days", 0)
    monkeypatch.setattr(settings, "audit_retention_days", 30)
    monkeypatch.setattr(settings, "retention_dry_run", False)

    result = run_retention_cycle(now=now, store=store, cache=MemoryCache())

    assert result["audit_events_matched"] == 1
    assert result["archived_events_matched"] == 1
    assert result["audit_events_deleted"] == 1
    assert result["archived_events_deleted"] == 1
    with store._get_conn() as conn:
        live = conn.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()
        archived = conn.execute("SELECT COUNT(*) AS n FROM audit_events_archive").fetchone()
    assert live["n"] == 0
    assert archived["n"] == 0


def test_batch_size_bounds_one_sweep(store, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    sessions = [_create_session(store, tenant_id=f"tenant-{i}") for i in range(3)]
    for ctx in sessions:
        _backdate_session(store, ctx.session_id, now - timedelta(days=400))

    monkeypatch.setattr(settings, "session_retention_days", 30)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", False)
    monkeypatch.setattr(settings, "retention_batch_size", 1)

    result = run_retention_cycle(now=now, store=store, cache=MemoryCache())

    assert result["sessions_matched"] == 3
    assert result["sessions_purged"] == 1
    remaining = [ctx for ctx in sessions if store.load(ctx.session_id, ctx.tenant_id) is not None]
    assert len(remaining) == 2


def test_zero_retention_days_means_forever(store, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    ctx = _create_session(store)
    _backdate_session(store, ctx.session_id, now - timedelta(days=400))

    monkeypatch.setattr(settings, "session_retention_days", 0)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", False)

    result = run_retention_cycle(now=now, store=store, cache=MemoryCache())

    assert result["sessions_matched"] == 0
    assert result["sessions_purged"] == 0
    assert store.load(ctx.session_id, "tenant-a") is not None


def test_repeated_sweep_is_idempotent(store, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    ctx = _create_session(store)
    _backdate_session(store, ctx.session_id, now - timedelta(days=400))
    cache = MemoryCache()

    monkeypatch.setattr(settings, "session_retention_days", 30)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", False)

    first = run_retention_cycle(now=now, store=store, cache=cache)
    second = run_retention_cycle(now=now, store=store, cache=cache)

    assert first["sessions_purged"] == 1
    assert second["sessions_matched"] == 0
    assert second["sessions_purged"] == 0
    assert second["errors_count"] == 0
    assert store.load(ctx.session_id, "tenant-a") is None


def test_purge_failure_is_recorded_and_retried_next_sweep(store, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    ctx = _create_session(store)
    _backdate_session(store, ctx.session_id, now - timedelta(days=400))
    cache = MemoryCache()

    original = store.purge_session
    calls = {"count": 0}

    def flaky_purge(session_id, tenant_id, purged_by, summary):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated purge failure")
        return original(session_id, tenant_id, purged_by, summary)

    monkeypatch.setattr(store, "purge_session", flaky_purge)
    monkeypatch.setattr(settings, "session_retention_days", 30)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", False)

    first = run_retention_cycle(now=now, store=store, cache=cache)

    assert first["sessions_matched"] == 1
    assert first["sessions_purged"] == 0
    assert first["errors_count"] == 1
    assert first["errors"][0]["stage"] == "purge"
    assert store.load(ctx.session_id, "tenant-a") is not None

    second = run_retention_cycle(now=now, store=store, cache=cache)

    assert second["sessions_purged"] == 1
    assert second["errors_count"] == 0
    assert store.load(ctx.session_id, "tenant-a") is None


def test_checkpoint_cleanup_failure_keeps_session_deleted(store, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    ctx = _create_session(store)
    _backdate_session(store, ctx.session_id, now - timedelta(days=400))

    def broken_checkpoint_cleanup(ctx_arg, *, persistent=False):
        raise RuntimeError("checkpoint store unavailable")

    monkeypatch.setattr(
        "graph.checkpoint_manager.delete_session_checkpoints",
        broken_checkpoint_cleanup,
    )
    monkeypatch.setattr(settings, "session_retention_days", 30)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", False)

    result = run_retention_cycle(now=now, store=store, cache=MemoryCache())

    assert result["sessions_purged"] == 1
    assert result["errors_count"] == 1
    assert result["errors"][0]["stage"] == "checkpoint_cleanup"
    with store._get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE session_id = ?",
            (ctx.session_id,),
        ).fetchone()
    assert row["n"] == 0


def test_sqlite_backup_restore_preserves_session(tmp_path, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    db_path = tmp_path / "retention_backup.db"
    backup_path = tmp_path / "retention_backup_copy.db"
    store = SQLiteSessionStore(db_path=str(db_path))
    store.initialize()
    ctx = _create_session(store)
    _backdate_session(store, ctx.session_id, now - timedelta(days=400))

    # SQLite WAL 模式下先把数据落回主文件，再复制为备份。
    checkpoint_conn = store._get_conn()
    try:
        checkpoint_conn.execute("PRAGMA wal_checkpoint(FULL)")
        checkpoint_conn.commit()
    finally:
        checkpoint_conn.close()
    shutil.copy2(db_path, backup_path)

    monkeypatch.setattr(settings, "session_retention_days", 30)
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    monkeypatch.setattr(settings, "retention_dry_run", False)
    run_retention_cycle(now=now, store=store, cache=MemoryCache())
    assert store.load(ctx.session_id, "tenant-a") is None

    gc.collect()
    for suffix in ("-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    shutil.copy2(backup_path, db_path)

    restored = SQLiteSessionStore(db_path=str(db_path))
    restored.initialize()
    restored_ctx = restored.load(ctx.session_id, "tenant-a")

    assert restored_ctx is not None
    assert restored_ctx.session_id == ctx.session_id
