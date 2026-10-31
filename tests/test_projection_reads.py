# tests/test_projection_reads.py
"""投影表读取层与轻量概览端点契约。

覆盖：
- SQLite TEXT 与 PostgreSQL JSONB 两种行进形状的模型转换；
- 投影直读与旧上下文路径返回结构一致；
- 空集合是合法结果；会话不存在返回 None（服务层仍抛 ValueError -> 404）；
- 租户隔离；读取过滤；服务层不再为列表端点解析整份上下文。
"""

from __future__ import annotations

import pytest

from core.models import (
    AuditEvent,
    EvalCase,
    EvalDataset,
    EvalExperiment,
    EvalRun,
    EvidenceSource,
    InterruptRecord,
    PendingHumanAction,
    ProjectContext,
    RedTeamCase,
    SafetyFinding,
)
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.projection_read import build_model

TENANT = "tenant-a"
SESSION_ID = "s-projection"


def _ctx_with_collections() -> ProjectContext:
    ctx = ProjectContext(session_id=SESSION_ID, tenant_id=TENANT)
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            action_type="approve",
            title="t",
            description="d",
        )
    )
    ctx.evidence_sources.append(
        EvidenceSource(
            session_id=ctx.session_id,
            title="evidence",
            source_type="paper",
            claims=["c1"],
            used_by_failure_mode_ids=["FM-1"],
        )
    )
    ctx.safety_findings.append(
        SafetyFinding(
            session_id=ctx.session_id,
            risk_type="unsupported_claim",
            severity="medium",
            location="L",
            description="d",
            recommended_action="r",
        )
    )
    ctx.audit_events.append(
        AuditEvent(
            session_id=ctx.session_id,
            actor="system",
            event_type="seeded",
            target_type="session",
            target_id=ctx.session_id,
        )
    )
    eval_case = EvalCase(
        session_id=ctx.session_id,
        input_payload="p",
        expected_behavior="e",
        pass_criteria=["must refuse"],
    )
    ctx.eval_cases.append(eval_case)
    ctx.eval_runs.append(
        EvalRun(
            session_id=ctx.session_id,
            eval_id=eval_case.eval_id,
            input_payload="p",
            expected_behavior="e",
            pass_criteria=["must refuse"],
            llm_judge_suggestion={"label": "passed", "rationale": "matched criteria"},
        )
    )
    dataset = EvalDataset(session_id=ctx.session_id, name="ds")
    ctx.eval_datasets.append(dataset)
    ctx.eval_experiments.append(
        EvalExperiment(session_id=ctx.session_id, dataset_id=dataset.dataset_id, name="exp")
    )
    ctx.redteam_cases.append(
        RedTeamCase(
            session_id=ctx.session_id,
            prompt="p",
            expected_failure_mode="fm",
            expected_safe_behavior="safe",
        )
    )
    ctx.interrupt_records.append(
        InterruptRecord(
            session_id=ctx.session_id,
            action_id=ctx.pending_actions[0].action_id,
            stage_id=1,
        )
    )
    return ctx


@pytest.fixture
def store(tmp_path) -> SQLiteSessionStore:
    backend = SQLiteSessionStore(str(tmp_path / "workflow.db"))
    backend.initialize()
    return backend


def _by_key(rows: list[dict], key: str) -> list[dict]:
    return sorted(rows, key=lambda row: row[key])


@pytest.mark.parametrize(
    ("table", "collection_attr", "key"),
    [
        ("human_actions", "pending_actions", "action_id"),
        ("evidence_sources", "evidence_sources", "evidence_id"),
        ("safety_findings", "safety_findings", "finding_id"),
        ("audit_events", "audit_events", "event_id"),
        ("eval_cases", "eval_cases", "eval_id"),
        ("eval_runs", "eval_runs", "run_id"),
        ("eval_datasets", "eval_datasets", "dataset_id"),
        ("eval_experiments", "eval_experiments", "experiment_id"),
        ("redteam_cases", "redteam_cases", "redteam_case_id"),
        ("interrupt_records", "interrupt_records", "interrupt_id"),
    ],
)
def test_projection_rows_match_context_dumps(store, table, collection_attr, key) -> None:
    ctx = _ctx_with_collections()
    store.save(ctx)

    expected = [item.model_dump(mode="json") for item in getattr(ctx, collection_attr)]
    actual = store.list_projection(table, ctx.session_id, ctx.tenant_id)

    assert actual is not None
    assert _by_key(actual, key) == _by_key(expected, key)


def test_projection_returns_empty_for_existing_session(store) -> None:
    ctx = ProjectContext(session_id="s-empty", tenant_id=TENANT)
    store.save(ctx)

    assert store.list_projection("evidence_sources", ctx.session_id, TENANT) == []
    assert store.list_projection("audit_events", ctx.session_id, TENANT) == []


def test_projection_returns_none_for_missing_session(store) -> None:
    assert store.list_projection("evidence_sources", "missing", TENANT) is None


def test_projection_enforces_tenant_ownership(store) -> None:
    ctx = ProjectContext(session_id="s-tenant", tenant_id="tenant-a")
    ctx.evidence_sources.append(EvidenceSource(session_id=ctx.session_id, title="e"))
    store.save(ctx)

    assert store.list_projection("evidence_sources", ctx.session_id, "tenant-b") is None
    assert store.list_projection("evidence_sources", ctx.session_id, "tenant-a") is not None


def test_projection_filters_by_status(store) -> None:
    ctx = ProjectContext(session_id="s-filter", tenant_id=TENANT)
    ctx.pending_actions.extend(
        [
            PendingHumanAction(
                session_id=ctx.session_id,
                stage_id=1,
                action_type="approve",
                title="pending",
                description="d",
            ),
            PendingHumanAction(
                session_id=ctx.session_id,
                stage_id=1,
                action_type="approve",
                title="resolved",
                description="d",
                status="resolved",
            ),
        ]
    )
    store.save(ctx)

    rows = store.list_projection("human_actions", ctx.session_id, TENANT, {"status": "pending"})
    assert rows is not None
    assert [row["title"] for row in rows] == ["pending"]


def test_build_model_accepts_text_and_object_json() -> None:
    base_row = {
        "evidence_id": "EV-1",
        "session_id": SESSION_ID,
        "title": "evidence",
        "url": None,
        "source_type": "paper",
        "credibility_score": 0.5,
        "summary": "",
        "verified": 0,
        "verified_by": None,
        "verified_at": None,
        "verification_note": "",
        "retrieved_at": "2026-01-01T00:00:00",
    }
    sqlite_row = {**base_row, "claims": '["c1"]', "used_by_failure_mode_ids": '["FM-1"]'}
    postgres_row = {**base_row, "claims": ["c1"], "used_by_failure_mode_ids": ["FM-1"]}

    sqlite_dump = build_model("evidence_sources", sqlite_row).model_dump(mode="json")
    postgres_dump = build_model("evidence_sources", postgres_row).model_dump(mode="json")

    assert sqlite_dump == postgres_dump


@pytest.fixture
def isolated_service(tmp_path, monkeypatch):
    from core import session_service as session_service_module

    backend = SQLiteSessionStore(str(tmp_path / "workflow.db"))
    backend.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    monkeypatch.setattr(session_service_module, "session_store", backend)
    monkeypatch.setattr(session_service_module, "context_cache", cache)
    return session_service_module.SessionService(), backend


def test_service_list_uses_projection_without_loading_context(
    isolated_service, monkeypatch
) -> None:
    service, backend = isolated_service
    ctx = ProjectContext(session_id="s-service", tenant_id=TENANT)
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            action_type="approve",
            title="t",
            description="d",
        )
    )
    backend.save(ctx)

    def _fail(*args, **kwargs):
        raise AssertionError("list_actions must not load the full context")

    monkeypatch.setattr(type(service), "get_session", _fail)

    rows = service.list_actions("s-service", tenant_id=TENANT)
    assert rows[0]["title"] == "t"


def test_service_keeps_empty_collection_contract(isolated_service, monkeypatch) -> None:
    service, backend = isolated_service
    backend.save(ProjectContext(session_id="s-empty", tenant_id=TENANT))

    def _fail(*args, **kwargs):
        raise AssertionError("empty projection must not fall back to context")

    monkeypatch.setattr(type(service), "get_session", _fail)
    assert service.list_evidence("s-empty", tenant_id=TENANT) == []


def test_service_raises_for_missing_session(isolated_service) -> None:
    service, _backend = isolated_service
    with pytest.raises(ValueError):
        service.list_evidence("missing", tenant_id=TENANT)


def test_session_overview_contract(isolated_service) -> None:
    service, _backend = isolated_service
    ctx = service.create_session(tenant_id=TENANT)
    ctx.flagged_items = []
    overview = service.get_session_overview(ctx.session_id, tenant_id=TENANT)

    assert overview is not None
    assert set(overview) == {
        "session_id",
        "session_name",
        "current_state",
        "selected_scenario_id",
        "data_classification",
        "created_at",
        "updated_at",
        "conversation_history",
        "flagged_items",
        "pending_actions",
    }
    assert overview["data_classification"] == "business_internal"
    assert service.get_session_overview("missing", tenant_id=TENANT) is None


def test_gzip_middleware_is_registered() -> None:
    pytest.importorskip("fastapi")
    from fastapi.middleware.gzip import GZipMiddleware

    from api.main import app

    assert any(middleware.cls is GZipMiddleware for middleware in app.user_middleware)
