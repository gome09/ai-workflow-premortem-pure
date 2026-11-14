# tests/test_business_closure_evidence.py
"""Evidence lifecycle and high-risk evidence gate regressions."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.evidence_service import link_failure_modes_to_evidence
from core.gates.engine import evaluate_stage_gate
from core.models import (
    EvidenceSource,
    FailureMode,
    PendingHumanAction,
    ProjectContext,
    SessionState,
    Stage1Output,
)
from core.oversight_service import create_actions_from_evidence_gaps, resolve_action
from core.report_service import build_evidence_summary
from core.services.evidence import EvidenceService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "tenant-evidence-scope"


@pytest.fixture
def gate_store(tmp_path, monkeypatch):
    store = SQLiteSessionStore(str(tmp_path / "evidence.db"))
    store.initialize()
    monkeypatch.setattr("storage.session_store.session_store", store)
    return store


def _ctx(*, verified: bool = False, referenced: bool = True) -> ProjectContext:
    ctx = ProjectContext(
        research_target="GPT-4o",
        domain="法律文书生成",
        goal="降低虚构条文引用",
        created_by="creator-user",
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.S1_REVIEW
    ctx.evidence_sources.append(
        EvidenceSource(
            evidence_id="EVID-1",
            session_id=ctx.session_id,
            title="Official evaluation report",
            source_type="official_doc",
            credibility_score=0.9,
            verified=verified,
            verified_by="reviewer" if verified else None,
        )
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="虚构不存在的法律条文",
                severity="high",
                evidence_ids=["EVID-1"] if referenced else [],
            )
        ]
    )
    ctx.stage_output_versions["stage_1"] = 1
    link_failure_modes_to_evidence(ctx)
    return ctx


def test_unverified_evidence_blocks_high_risk_gate(gate_store):
    ctx = _ctx(verified=False)
    gate_store.create(ctx)

    result = evaluate_stage_gate(ctx, 1)

    assert result.can_continue is False
    blocker = next(item for item in result.blockers if item.blocker_type == "evidence_gap")
    assert blocker.required_resolution == "verify_evidence"
    assert blocker.can_be_overridden_by_approval is False
    assert blocker.source_id == "EVID-1"


def test_unverified_referenced_evidence_is_not_adopted():
    ctx = _ctx(verified=False)
    evidence = ctx.evidence_sources[0]
    assert evidence.lifecycle_status == "submitted"
    assert evidence.used_by_failure_mode_ids == ["FM-001"]

    evidence.verified = True
    evidence.verified_by = "reviewer"
    assert evidence.lifecycle_status == "adopted"


def test_verified_unreferenced_evidence_is_not_adopted():
    ctx = _ctx(verified=True, referenced=False)
    evidence = ctx.evidence_sources[0]
    assert evidence.lifecycle_status == "verified"
    assert evidence.used_by_failure_mode_ids == []


def test_removing_failure_mode_reference_downgrades_adoption():
    ctx = _ctx(verified=True, referenced=True)
    evidence = ctx.evidence_sources[0]
    assert evidence.lifecycle_status == "adopted"

    ctx.stage_1_output.failure_modes[0].evidence_ids = []
    link_failure_modes_to_evidence(ctx)

    assert evidence.used_by_failure_mode_ids == []
    assert evidence.lifecycle_status == "verified"


def test_dismiss_action_does_not_clear_evidence_gate(gate_store):
    ctx = _ctx(verified=False)
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            source_type="evidence_unverified_for_high_risk",
            source_id="FM-001",
            action_type="verify_evidence",
            title="核验证据",
            description="unverified",
            risk_level="high",
            blocking=True,
            stage_output_version=1,
        )
    )
    gate_store.create(ctx)
    action = ctx.pending_actions[0]

    # Simulate the dismiss outcome without relying on the generic resolution
    # helper (which returns early for verify_evidence dismissals). The gate
    # must still see unverified evidence.
    action.status = "resolved"
    action.reviewer_decision = "dismissed"
    gate_store.save(ctx)

    result = evaluate_stage_gate(ctx, 1)
    assert result.can_continue is False
    assert any(item.blocker_type == "evidence_gap" for item in result.blockers)
    assert ctx.evidence_sources[0].verified is False


def test_evidence_summary_counts_lifecycle():
    ctx = _ctx(verified=False)
    ctx.evidence_sources.append(
        EvidenceSource(
            evidence_id="EVID-2",
            session_id=ctx.session_id,
            title="Verified but unreferenced",
            source_type="paper",
            credibility_score=0.8,
            verified=True,
            verified_by="reviewer",
        )
    )
    ctx.evidence_sources[0].verified = True
    ctx.evidence_sources[0].verified_by = "reviewer"

    summary = build_evidence_summary(ctx)

    assert summary["lifecycle_counts"] == {"submitted": 0, "verified": 1, "adopted": 1}
    assert summary["verified_sources"] == 2
    assert summary["stage_1_version"] == 1
    assert summary["adopted_evidence"][0]["linked_failure_mode_ids"] == ["FM-001"]


@pytest.fixture
def evidence_scope_env(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "evidence-scope.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield store


def _high_risk_ctx(evidence_ids: list[str]) -> ProjectContext:
    ctx = ProjectContext(
        tenant_id=_TENANT,
        research_target="GPT-4o",
        domain="法律文书生成",
        goal="降低虚构条文引用",
        created_by="creator-user",
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.S1_REVIEW
    for index, evidence_id in enumerate(evidence_ids, 1):
        ctx.evidence_sources.append(
            EvidenceSource(
                evidence_id=evidence_id,
                session_id=ctx.session_id,
                title=f"Official report {index}",
                source_type="official_doc",
                credibility_score=0.9,
            )
        )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="虚构不存在的法律条文",
                severity="high",
                evidence_ids=list(evidence_ids),
            )
        ]
    )
    ctx.stage_output_versions["stage_1"] = 1
    link_failure_modes_to_evidence(ctx)
    created = create_actions_from_evidence_gaps(ctx, stage=1)
    assert len(created) == 1
    return ctx


def _reload(service: EvidenceService, session_id: str) -> ProjectContext:
    stored = service.get_session(session_id, tenant_id=_TENANT)
    assert stored is not None
    return stored


def test_single_verify_only_changes_target_evidence(evidence_scope_env):
    ctx = _high_risk_ctx(["EVID-1", "EVID-2"])
    action_id = ctx.pending_actions[0].action_id
    evidence_scope_env.create(ctx)

    service = EvidenceService()
    service.verify_evidence(ctx.session_id, "EVID-1", note="只核验 E1", tenant_id=_TENANT)

    stored = _reload(service, ctx.session_id)
    evidence = {item.evidence_id: item for item in stored.evidence_sources}
    assert evidence["EVID-1"].verified is True
    assert evidence["EVID-2"].verified is False
    action = next(item for item in stored.pending_actions if item.action_id == action_id)
    assert action.status == "pending"

    gate = evaluate_stage_gate(stored, 1)
    assert any(
        blocker.blocker_type == "evidence_gap" and blocker.source_id == "EVID-2"
        for blocker in gate.blockers
    )
    assert not any(
        blocker.blocker_type == "evidence_gap" and blocker.source_id == "EVID-1"
        for blocker in gate.blockers
    )


def test_action_closes_after_all_sources_verified_without_overwriting_first(evidence_scope_env):
    ctx = _high_risk_ctx(["EVID-1", "EVID-2"])
    action_id = ctx.pending_actions[0].action_id
    evidence_scope_env.create(ctx)

    service = EvidenceService()
    service.verify_evidence(ctx.session_id, "EVID-1", note="first verify", tenant_id=_TENANT)
    first = {item.evidence_id: item for item in _reload(service, ctx.session_id).evidence_sources}[
        "EVID-1"
    ]
    first_by = first.verified_by
    first_at = first.verified_at
    first_note = first.verification_note

    service.verify_evidence(ctx.session_id, "EVID-2", note="second verify", tenant_id=_TENANT)

    stored = _reload(service, ctx.session_id)
    evidence = {item.evidence_id: item for item in stored.evidence_sources}
    assert evidence["EVID-1"].verified_by == first_by
    assert evidence["EVID-1"].verified_at == first_at
    assert evidence["EVID-1"].verification_note == first_note
    assert evidence["EVID-2"].verified is True
    assert evidence["EVID-2"].verification_note == "second verify"
    action = next(item for item in stored.pending_actions if item.action_id == action_id)
    assert action.status == "resolved"


def test_explicit_action_verification_keeps_bulk_semantics(evidence_scope_env):
    ctx = _high_risk_ctx(["EVID-1", "EVID-2"])
    action = ctx.pending_actions[0]
    evidence_scope_env.create(ctx)

    # 模拟 E1 已被历史核验：显式整组核验不得覆盖其身份与时间。
    verified_at = ctx.evidence_sources[0].verified_at
    ctx.evidence_sources[0].verified = True
    ctx.evidence_sources[0].verified_by = "alice"
    ctx.evidence_sources[0].verification_note = "historic verify"
    evidence_scope_env.save(ctx)

    resolve_action(ctx, action_id=action.action_id, decision="verify_evidence", note="whole action")
    evidence_scope_env.save(ctx)

    stored = _reload(EvidenceService(), ctx.session_id)
    evidence = {item.evidence_id: item for item in stored.evidence_sources}
    assert evidence["EVID-1"].verified_by == "alice"
    assert evidence["EVID-1"].verification_note == "historic verify"
    assert evidence["EVID-1"].verified_at == verified_at
    assert evidence["EVID-2"].verified is True
    assert evidence["EVID-2"].verified_by == "user"
    assert next(
        item for item in stored.pending_actions if item.action_id == action.action_id
    ).status == ("resolved")


def test_shared_evidence_closes_only_satisfied_actions(evidence_scope_env):
    ctx = ProjectContext(
        tenant_id=_TENANT,
        research_target="GPT-4o",
        domain="法律文书生成",
        goal="降低虚构条文引用",
        created_by="creator-user",
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.S1_REVIEW
    for evidence_id in ("EVID-1", "EVID-2"):
        ctx.evidence_sources.append(
            EvidenceSource(
                evidence_id=evidence_id,
                session_id=ctx.session_id,
                title=f"Report {evidence_id}",
                source_type="official_doc",
                credibility_score=0.9,
            )
        )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="只引用 E1",
                severity="high",
                evidence_ids=["EVID-1"],
            ),
            FailureMode(
                id="FM-002",
                category="幻觉",
                description="同时引用 E1/E2",
                severity="high",
                evidence_ids=["EVID-1", "EVID-2"],
            ),
        ]
    )
    ctx.stage_output_versions["stage_1"] = 1
    link_failure_modes_to_evidence(ctx)
    created = create_actions_from_evidence_gaps(ctx, stage=1)
    assert len(created) == 2
    action_by_source = {item.source_id: item.action_id for item in created}
    evidence_scope_env.create(ctx)

    service = EvidenceService()
    service.verify_evidence(ctx.session_id, "EVID-1", note="shared", tenant_id=_TENANT)

    stored = _reload(service, ctx.session_id)
    status_by_id = {item.action_id: item.status for item in stored.pending_actions}
    assert status_by_id[action_by_source["FM-001"]] == "resolved"
    assert status_by_id[action_by_source["FM-002"]] == "pending"

    service.verify_evidence(ctx.session_id, "EVID-2", note="complete shared", tenant_id=_TENANT)
    stored = _reload(service, ctx.session_id)
    status_by_id = {item.action_id: item.status for item in stored.pending_actions}
    assert status_by_id[action_by_source["FM-002"]] == "resolved"


def test_single_verify_audit_not_duplicated(evidence_scope_env):
    ctx = _high_risk_ctx(["EVID-1", "EVID-2"])
    evidence_scope_env.create(ctx)

    service = EvidenceService()
    service.verify_evidence(ctx.session_id, "EVID-1", note="audit once", tenant_id=_TENANT)
    stored = _reload(service, ctx.session_id)
    events = [
        event
        for event in stored.audit_events
        if event.event_type == "evidence_verified" and event.target_id == "EVID-1"
    ]
    assert len(events) == 1

    service.verify_evidence(ctx.session_id, "EVID-2", note="audit once", tenant_id=_TENANT)
    stored = _reload(service, ctx.session_id)
    verified_events = [
        event for event in stored.audit_events if event.event_type == "evidence_verified"
    ]
    assert len(verified_events) == 2
    assert {event.target_id for event in verified_events} == {"EVID-1", "EVID-2"}
