from core.models import PendingHumanAction, ProjectContext, Stage1Output
from graph.transition_policy import evaluate_action_resolution, stage_can_continue


def test_reject_approve_action_blocks_stage_continue():
    ctx = ProjectContext()
    ctx.stage_1_output = Stage1Output()
    ctx.stage_output_versions["stage_1"] = 1
    action = PendingHumanAction(
        session_id=ctx.session_id,
        stage_id=1,
        action_type="approve",
        title="high risk",
        description="high risk",
        status="resolved",
        reviewer_decision="reject",
        blocking=True,
        stage_output_version=1,
    )
    ctx.pending_actions.append(action)

    can_continue, reason = stage_can_continue(ctx, 1)
    assert can_continue is False
    assert "驳回" in reason


def test_escalate_cannot_be_rejected():
    action = PendingHumanAction(
        session_id="s1",
        stage_id=1,
        action_type="escalate",
        title="critical risk",
        description="critical risk",
        risk_level="critical",
    )
    effect = evaluate_action_resolution(action, "reject")
    assert effect.allow_resolve is False
    assert effect.require_escalation is True


def test_edit_requires_payload_after():
    action = PendingHumanAction(
        session_id="s1",
        stage_id=3,
        action_type="edit",
        title="edit",
        description="edit",
    )
    effect = evaluate_action_resolution(action, "edit", payload_after=None)
    assert effect.allow_resolve is False
