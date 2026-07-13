# tests/test_oversight_service.py
from __future__ import annotations

from core.models import (
    EvidenceSource,
    FailureMode,
    FlaggedItem,
    FlagStatus,
    ProjectContext,
    Stage1Output,
)
from core.oversight_service import create_review_actions_for_stage, resolve_action


def test_flag_creates_verify_evidence_action():
    ctx = ProjectContext()
    ctx.flagged_items = [
        FlaggedItem(stage=1, content="【需核验】某项证据", status=FlagStatus.PENDING)
    ]

    created = create_review_actions_for_stage(ctx, stage=1)

    assert len(created) == 1
    assert created[0].action_type == "verify_evidence"
    assert ctx.has_blocking_actions(stage=1)


def test_high_failure_mode_creates_approve_action_once_when_evidence_is_verified():
    ctx = ProjectContext()
    ctx.evidence_sources = [
        EvidenceSource(
            evidence_id="EVID-001",
            session_id=ctx.session_id,
            title="Verified test evidence",
            source_type="official_doc",
            credibility_score=0.9,
            summary="测试记录",
            verified=True,
        )
    ]
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="虚构事实",
                severity="high",
                evidence="测试记录",
                evidence_ids=["EVID-001"],
            )
        ]
    )

    first = create_review_actions_for_stage(ctx, stage=1)
    second = create_review_actions_for_stage(ctx, stage=1)

    assert len(first) == 1
    assert len(second) == 0
    assert first[0].action_type == "approve"
    assert first[0].source_type == "failure_mode"
    assert first[0].source_id == "FM-001"


def test_high_failure_mode_without_evidence_id_creates_evidence_gap_edit_action():
    ctx = ProjectContext()
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="虚构事实",
                severity="high",
                evidence="测试记录",
            )
        ]
    )

    created = create_review_actions_for_stage(ctx, stage=1)

    assert {action.source_type for action in created} == {"failure_mode", "evidence_gap"}
    evidence_gap = next(action for action in created if action.source_type == "evidence_gap")
    assert evidence_gap.action_type == "edit"
    assert evidence_gap.blocking is True
    assert evidence_gap.payload_before["requires_structured_output"] is True
    assert evidence_gap.payload_before["expected_schema"] == "Stage1Schema"


def test_resolve_action_updates_status_and_audit():
    ctx = ProjectContext()
    ctx.flagged_items = [
        FlaggedItem(stage=1, content="【需核验】某项证据", status=FlagStatus.PENDING)
    ]
    action = create_review_actions_for_stage(ctx, stage=1)[0]

    resolve_action(ctx, action_id=action.action_id, decision="verify_evidence", note="已核验")

    assert ctx.pending_actions[0].status == "resolved"
    assert ctx.flagged_items[0].status == FlagStatus.VERIFIED
    assert any(e.event_type == "human_action_resolved" for e in ctx.audit_events)
