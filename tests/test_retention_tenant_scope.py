# tests/test_retention_tenant_scope.py
"""Milestone 1 P3: retention 删除必须覆盖派生数据，且绝不跨 tenant。

验收：
- purge_session 删除会话后，所有带 session_id 的派生表归零（FK CASCADE + 显式
  gate_evaluation_records 清理），审计证据转入 archive 表保留。
- 同一 session_id 在其它 tenant 的 gate 记录不会被误删。
- 其它会话（不同 tenant / 不同 session）完全不受影响。
"""

from __future__ import annotations

import uuid

import pytest

from core.audit_service import append_audit_event
from core.models import (
    EvalCase,
    EvalDataset,
    EvalRun,
    EvidenceSource,
    LLMTrace,
    PendingHumanAction,
    ProjectContext,
    ReportArtifact,
    SafetyFinding,
    SessionState,
)
from storage.backends.sqlite_store import SQLiteSessionStore


@pytest.fixture
def store(tmp_path):
    backend = SQLiteSessionStore(db_path=str(tmp_path / "retention_scope.db"))
    backend.initialize()
    return backend


def _session_tables(store: SQLiteSessionStore) -> list[str]:
    """所有带 session_id 列的表（含非 FK 的 gate_evaluation_records）。"""
    tables: list[str] = []
    with store._get_conn() as conn:  # noqa: SLF001
        names = [
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        for name in names:
            columns = [
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({name})").fetchall()  # noqa: S608
            ]
            if "session_id" in columns:
                tables.append(name)
    return tables


def _count(store: SQLiteSessionStore, table: str, session_id: str) -> int:
    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE session_id = ?",  # noqa: S608
            (session_id,),
        ).fetchone()
    return int(row["n"])


def _insert_gate_row(store: SQLiteSessionStore, session_id: str, tenant_id: str) -> None:
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO gate_evaluation_records "
            "(record_id, session_id, tenant_id, stage_id, risk_tier, passed, "
            " blocking_rule_ids, rule_versions, evaluated_at) "
            "VALUES (?, ?, ?, 1, 'low', 1, '[]', '{}', CURRENT_TIMESTAMP)",
            (str(uuid.uuid4()), session_id, tenant_id),
        )
        conn.commit()


def _build_ctx(tenant_id: str, name: str) -> ProjectContext:
    ctx = ProjectContext(tenant_id=tenant_id, session_name=name)
    ctx.current_state = SessionState.S1_REVIEW
    ctx.pending_actions = [
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            action_type="edit",
            title="待处理动作",
            description="动作描述",
        )
    ]
    ctx.evidence_sources = [
        EvidenceSource(
            session_id=ctx.session_id,
            title="证据",
            source_type="user_material",
            summary="证据摘要",
        )
    ]
    ctx.safety_findings = [
        SafetyFinding(
            session_id=ctx.session_id,
            stage_id=1,
            risk_type="sensitive_info",
            severity="low",
            location="session",
            description="安全发现",
            recommended_action="人工复核",
        )
    ]
    ctx.report_artifacts = [
        ReportArtifact(
            session_id=ctx.session_id,
            version="v1",
            content_markdown="报告正文",
            content_json={"conclusion": "结论"},
        )
    ]
    case = EvalCase(session_id=ctx.session_id, input_payload="输入", expected_behavior="预期")
    ctx.eval_cases = [case]
    ctx.eval_runs = [
        EvalRun(
            session_id=ctx.session_id,
            eval_id=case.eval_id,
            input_payload="输入",
            expected_behavior="预期",
        )
    ]
    ctx.eval_datasets = [
        EvalDataset(session_id=ctx.session_id, name="数据集", case_ids=[case.eval_id])
    ]
    ctx.llm_traces = [LLMTrace(session_id=ctx.session_id, node_name="stage_1")]
    append_audit_event(
        ctx,
        actor="system",
        event_type="retention_probe",
        target_type="session",
        target_id=ctx.session_id,
    )
    return ctx


def _archive_count(store: SQLiteSessionStore, session_id: str) -> int:
    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_events_archive WHERE original_session_id = ?",
            (session_id,),
        ).fetchone()
    return int(row["n"])


def test_purge_removes_all_derived_data_and_keeps_archive(store):
    ctx_a = _build_ctx("tenant-a", "retention-a")
    store.save(ctx_a)
    store.log_event(ctx_a.session_id, "message", 1, {"state": "s1_review"})
    _insert_gate_row(store, ctx_a.session_id, "tenant-a")

    ctx_b = _build_ctx("tenant-b", "retention-b")
    store.save(ctx_b)
    _insert_gate_row(store, ctx_b.session_id, "tenant-b")

    tables = _session_tables(store)
    before = {table: _count(store, table, ctx_a.session_id) for table in tables}
    for expected_table in (
        "sessions",
        "human_actions",
        "evidence_sources",
        "safety_findings",
        "report_artifacts",
        "eval_cases",
        "eval_runs",
        "eval_datasets",
        "llm_traces",
        "audit_events",
        "session_events",
        "gate_evaluation_records",
    ):
        assert before[expected_table] >= 1, (expected_table, before)

    archived = store.purge_session(
        ctx_a.session_id,
        "tenant-a",
        purged_by="retention",
        summary={"reason": "session_retention_days"},
    )
    # 原审计事件 + session_purged 事件都进入 archive。
    assert archived >= 2
    assert _archive_count(store, ctx_a.session_id) == archived

    after = {table: _count(store, table, ctx_a.session_id) for table in tables}
    residual = {table: n for table, n in after.items() if n}
    assert residual == {}, residual

    # 另一个 tenant 的会话与治理记录完全不受影响。
    assert _count(store, "sessions", ctx_b.session_id) == 1
    assert _count(store, "gate_evaluation_records", ctx_b.session_id) == 1
    assert store.load(ctx_b.session_id, "tenant-b") is not None
    assert store.load(ctx_a.session_id, "tenant-a") is None


def test_purge_does_not_touch_same_session_id_in_other_tenant(store):
    ctx_a = _build_ctx("tenant-a", "retention-a")
    store.save(ctx_a)
    _insert_gate_row(store, ctx_a.session_id, "tenant-a")
    # 历史数据里可能存在同 session_id 但 tenant 不一致的治理残留（如租户回填前）。
    _insert_gate_row(store, ctx_a.session_id, "tenant-b")

    store.purge_session(ctx_a.session_id, "tenant-a", purged_by="retention", summary={})

    with store._get_conn() as conn:  # noqa: SLF001
        rows = conn.execute(
            "SELECT tenant_id FROM gate_evaluation_records WHERE session_id = ?",
            (ctx_a.session_id,),
        ).fetchall()
    assert [row["tenant_id"] for row in rows] == ["tenant-b"]
