# tests/test_projection_sync_state.py
"""save() 差分同步：状态计算、计划逻辑与 SQLite 落库行为。

覆盖：
- hash 集合内容不变时跳过重写，变化时回退全量；
- append 集合只追加尾部，集合缩短或尾部不匹配时回退全量；
- 状态缺失/损坏/模式不符时 fail-safe 全量同步；
- SQLite UPSERT 不会因投影子表级联删除而丢失未重写的数据；
- 旧库 initialize() 幂等补齐 V009 列。
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from core.models import AuditEvent, PendingHumanAction, ProjectContext
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.projection_state import COLLECTIONS, SyncPlan, compute_state, plan_sync

TENANT = "tenant-a"


def _ctx_with_action() -> ProjectContext:
    ctx = ProjectContext(session_id="s-sync", tenant_id=TENANT)
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            action_type="approve",
            title="t",
            description="d",
        )
    )
    return ctx


def _audit(ctx: ProjectContext, event_id: str) -> None:
    ctx.audit_events.append(
        AuditEvent(
            event_id=event_id,
            session_id=ctx.session_id,
            actor="system",
            event_type="seeded",
            target_type="session",
            target_id=ctx.session_id,
        )
    )


def test_compute_state_tracks_hash_and_append_cursors() -> None:
    ctx = _ctx_with_action()
    _audit(ctx, "EV-1")
    _audit(ctx, "EV-2")

    state = compute_state(ctx.model_dump(mode="json"))

    assert set(state) == set(COLLECTIONS)
    assert state["human_actions"]["mode"] == "hash"
    assert isinstance(state["human_actions"]["hash"], str)
    assert state["audit_events"] == {"mode": "append", "count": 2, "last_id": "EV-2"}


def test_plan_sync_skips_unchanged_collections() -> None:
    ctx = _ctx_with_action()
    data = ctx.model_dump(mode="json")
    state = compute_state(data)

    plans = plan_sync(state, state, data)

    assert all(plan.skip for plan in plans.values())


def test_plan_sync_full_syncs_hash_collection_when_content_changes() -> None:
    ctx = _ctx_with_action()
    previous = compute_state(ctx.model_dump(mode="json"))
    ctx.pending_actions[0].status = "resolved"
    data = ctx.model_dump(mode="json")

    plans = plan_sync(previous, compute_state(data), data)

    assert plans["human_actions"] == SyncPlan(start=0)
    assert plans["evidence_sources"].skip


def test_plan_sync_appends_only_tail_for_append_collections() -> None:
    ctx = _ctx_with_action()
    _audit(ctx, "EV-1")
    _audit(ctx, "EV-2")
    data = ctx.model_dump(mode="json")
    previous = compute_state(data)

    _audit(ctx, "EV-3")
    data_next = ctx.model_dump(mode="json")
    plans = plan_sync(previous, compute_state(data_next), data_next)

    assert plans["audit_events"] == SyncPlan(start=2)
    assert plans["llm_traces"].skip
    assert plans["human_actions"].skip


@pytest.mark.parametrize(
    "previous",
    [
        None,
        {},
        {"audit_events": {"mode": "append"}},
        {"audit_events": {"mode": "append", "count": "2", "last_id": "EV-1"}},
        {"audit_events": {"mode": "hash", "hash": "opaque"}},
    ],
)
def test_plan_sync_fails_safe_on_corrupt_state(previous) -> None:
    ctx = _ctx_with_action()
    _audit(ctx, "EV-1")
    _audit(ctx, "EV-2")
    data = ctx.model_dump(mode="json")

    plans = plan_sync(previous, compute_state(data), data)

    assert plans["audit_events"] == SyncPlan(start=0)
    assert not plans["human_actions"].skip


def test_plan_sync_falls_back_when_append_collection_shrinks() -> None:
    ctx = _ctx_with_action()
    _audit(ctx, "EV-1")
    _audit(ctx, "EV-2")
    previous = compute_state(ctx.model_dump(mode="json"))

    ctx.audit_events = ctx.audit_events[:1]
    data = ctx.model_dump(mode="json")
    plans = plan_sync(previous, compute_state(data), data)

    assert plans["audit_events"] == SyncPlan(start=0)


@pytest.fixture
def store(tmp_path) -> SQLiteSessionStore:
    backend = SQLiteSessionStore(str(tmp_path / "workflow.db"))
    backend.initialize()
    return backend


def _projection_state(db_path: str, session_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT projection_state FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    finally:
        conn.close()
    return json.loads(row[0]) if row and row[0] else {}


def test_sqlite_save_skips_unchanged_collections_and_keeps_rows(store, monkeypatch) -> None:
    ctx = _ctx_with_action()
    synced: list[int] = []
    original = store._sync_human_actions

    def recording_sync(conn, context):
        synced.append(1)
        original(conn, context)

    monkeypatch.setattr(store, "_sync_human_actions", recording_sync)

    store.save(ctx)
    first = store.list_projection("human_actions", ctx.session_id, TENANT)
    store.save(ctx)

    assert synced == [1]
    assert first is not None and len(first) == 1
    assert store.list_projection("human_actions", ctx.session_id, TENANT) == first


def test_sqlite_save_appends_only_new_audit_events(store, monkeypatch) -> None:
    ctx = _ctx_with_action()
    _audit(ctx, "EV-1")
    _audit(ctx, "EV-2")
    starts: list[int] = []
    original = store._sync_audit_events

    def recording_sync(conn, context, start=0):
        starts.append(start)
        original(conn, context, start=start)

    monkeypatch.setattr(store, "_sync_audit_events", recording_sync)

    store.save(ctx)
    _audit(ctx, "EV-3")
    store.save(ctx)

    rows = store.list_projection("audit_events", ctx.session_id, TENANT)
    assert rows is not None
    # 同一批事件 created_at 可能落在同一微秒，投影排序只保证时间序，不保证并列顺序。
    assert sorted(row["event_id"] for row in rows) == ["EV-1", "EV-2", "EV-3"]
    assert starts == [0, 2]


def test_sqlite_save_persists_projection_state(store) -> None:
    ctx = _ctx_with_action()

    store.save(ctx)

    assert _projection_state(store._db_path, ctx.session_id) == compute_state(
        ctx.model_dump(mode="json")
    )


def _columns(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}  # noqa: S608
    finally:
        conn.close()


def test_initialize_adds_v009_and_v010_columns_to_existing_database(tmp_path) -> None:
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, current_state TEXT NOT NULL "
        "DEFAULT 'init', context_json TEXT NOT NULL DEFAULT '{}', tenant_id TEXT, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE eval_runs (run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
        "eval_id TEXT NOT NULL, run_mode TEXT NOT NULL, input_payload TEXT NOT NULL, "
        "expected_behavior TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    SQLiteSessionStore(db_path).initialize()

    assert "projection_state" in _columns(db_path, "sessions")
    assert "context_digest" in _columns(db_path, "sessions")
    assert {"pass_criteria", "llm_judge_suggestion"} <= _columns(db_path, "eval_runs")
