# tests/test_business_closure_evidence.py
"""Evidence lifecycle and high-risk evidence gate regressions."""

from __future__ import annotations

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
from core.report_service import build_evidence_summary
from storage.backends.sqlite_store import SQLiteSessionStore


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
    gate_store.save(ctx)

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
    gate_store.save(ctx)
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
