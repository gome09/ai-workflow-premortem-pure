# tests/test_domain_services.py
"""Milestone 2: each domain service is independently unit-testable."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.models import (
    AuditEvent,
    EvalCase,
    EvidenceSource,
    FlaggedItem,
    FlagStatus,
    InterruptRecord,
    LLMTrace,
    ProjectContext,
    SessionState,
)
from core.oversight_service import create_review_actions_for_stage
from core.services.audit_trace import AuditTraceService
from core.services.evaluation import EvaluationService
from core.services.evidence import EvidenceService
from core.services.governance import GovernanceService
from core.services.session_workflow import SessionWorkflowService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


@pytest.fixture
def domain_env(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "domains.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield store


def test_session_workflow_service_is_independent(domain_env):
    service = SessionWorkflowService()
    ctx = service.create_session(tenant_id="tenant-a", scenario_id=None)
    assert ctx.current_state == SessionState.INIT

    renamed = service.rename_session(ctx.session_id, "domain rename", tenant_id="tenant-a")
    assert renamed["session_name"] == "domain rename"

    loaded = service.get_session(ctx.session_id, tenant_id="tenant-a")
    assert loaded is not None
    loaded.current_state = SessionState.ERROR
    loaded.last_error = "synthetic failure"
    domain_env.save(loaded)
    service._cache_delete(loaded.session_id, "tenant-a")
    recovered = service.recover_workflow(
        ctx.session_id, target_state="init", note="domain test", tenant_id="tenant-a"
    )
    assert recovered["after"] == SessionState.INIT.value


def test_governance_service_is_independent(domain_env):
    ctx = ProjectContext(tenant_id="tenant-a")
    ctx.flagged_items = [FlaggedItem(stage=1, content="【需核验】证据", status=FlagStatus.PENDING)]
    domain_env.save(ctx)
    action = create_review_actions_for_stage(ctx, stage=1)[0]
    domain_env.save(ctx)

    service = GovernanceService()
    resolved = service.resolve_action(
        ctx.session_id,
        action.action_id,
        decision="verify_evidence",
        note="domain test",
        tenant_id="tenant-a",
    )
    assert resolved.pending_actions[0].status == "resolved"
    assert resolved.flagged_items[0].status == FlagStatus.VERIFIED


def test_evidence_service_is_independent(domain_env):
    ctx = ProjectContext(tenant_id="tenant-a")
    ctx.evidence_sources = [
        EvidenceSource(
            evidence_id="EVID-1",
            session_id=ctx.session_id,
            title="evidence",
            source_type="official_doc",
            credibility_score=0.9,
            summary="reference",
        )
    ]
    domain_env.save(ctx)

    service = EvidenceService()
    result = service.verify_evidence(
        ctx.session_id, "EVID-1", note="domain test", tenant_id="tenant-a"
    )
    assert result["ok"] is True
    assert result["resolved_actions_count"] == 0
    stored = service.get_session(ctx.session_id, tenant_id="tenant-a")
    assert stored is not None
    assert stored.evidence_sources[0].verified is True


def test_evaluation_service_is_independent(domain_env):
    ctx = ProjectContext(tenant_id="tenant-a")
    ctx.eval_cases = [
        EvalCase(
            session_id=ctx.session_id,
            target_node_id="N-1",
            scenario_type="normal",
            input_payload="input",
            expected_behavior="safe",
        )
    ]
    domain_env.save(ctx)

    service = EvaluationService()
    result = service.score_eval_case(
        ctx.session_id,
        ctx.eval_cases[0].eval_id,
        human_score=4,
        human_comment="domain test",
        passed=True,
        tenant_id="tenant-a",
    )
    assert result["ok"] is True
    assert result["passed"] is True


def test_audit_trace_service_is_independent(domain_env):
    ctx = ProjectContext(tenant_id="tenant-a")
    ctx.llm_traces = [
        LLMTrace(session_id=ctx.session_id, stage=1, node_name="n1", parser_status="ok"),
        LLMTrace(session_id=ctx.session_id, stage=2, node_name="n2", parser_status="failed"),
    ]
    ctx.audit_events = [
        AuditEvent(
            session_id=ctx.session_id,
            actor="system",
            event_type="test_event",
            target_type="session",
            target_id=ctx.session_id,
        )
    ]
    ctx.interrupt_records = [
        InterruptRecord(session_id=ctx.session_id, action_id="A-1", stage_id=1)
    ]
    domain_env.save(ctx)

    service = AuditTraceService()
    traces = service.list_traces(ctx.session_id, parser_status="failed", tenant_id="tenant-a")
    assert [trace["node_name"] for trace in traces] == ["n2"]
    assert service.list_audit_events(ctx.session_id, tenant_id="tenant-a")[0]["event_type"] == (
        "test_event"
    )
    assert (
        service.get_interrupt_record(
            ctx.session_id, ctx.interrupt_records[0].interrupt_id, tenant_id="tenant-a"
        )["action_id"]
        == "A-1"
    )
