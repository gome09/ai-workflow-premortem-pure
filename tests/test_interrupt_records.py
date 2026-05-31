from __future__ import annotations

from core.models import PendingHumanAction, ProjectContext
from graph.interrupts import (
    mark_interrupt_cancelled_from_action,
    mark_interrupt_resumed_from_action,
    sync_interrupt_records,
)


class DummyEffect:
    def __init__(self, allow_continue: bool):
        self.allow_continue = allow_continue
        self.require_revision = not allow_continue
        self.require_escalation = False
        self.message = "allowed" if allow_continue else "blocked"


def _blocking_action(decision: str | None = None) -> PendingHumanAction:
    action = PendingHumanAction(
        session_id="s1",
        stage_id=1,
        source_type="failure_mode",
        source_id="FM-1",
        action_type="approve",
        risk_level="high",
        title="Approve high risk finding",
        description="Requires human approval.",
        blocking=True,
    )
    if decision is not None:
        action.status = "resolved"
        action.reviewer_decision = decision
    return action


def test_sync_creates_pending_interrupt_for_blocking_action():
    ctx = ProjectContext(session_id="s1")
    ctx.pending_actions.append(_blocking_action())

    created = sync_interrupt_records(ctx)

    assert len(created) == 1
    assert ctx.interrupt_records[0].status == "pending"
    assert ctx.interrupt_records[0].action_id == ctx.pending_actions[0].action_id
    assert ctx.interrupt_records[0].thread_id == ctx.session_id
    assert (
        ctx.interrupt_records[0].interrupt_payload["action_id"] == ctx.pending_actions[0].action_id
    )


def test_approve_resume_marks_interrupt_resumed():
    ctx = ProjectContext(session_id="s1")
    action = _blocking_action()
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)

    action.status = "resolved"
    action.reviewer_decision = "approve"
    mark_interrupt_resumed_from_action(ctx, action.action_id, policy_effect=DummyEffect(True))

    assert ctx.interrupt_records[0].status == "resumed"
    assert ctx.interrupt_records[0].resume_value["allow_continue"] is True


def test_reject_cancels_interrupt_instead_of_resuming():
    ctx = ProjectContext(session_id="s1")
    action = _blocking_action()
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)

    action.status = "resolved"
    action.reviewer_decision = "reject"
    mark_interrupt_cancelled_from_action(
        ctx, action.action_id, reason="Rejected", policy_effect=DummyEffect(False)
    )

    assert ctx.interrupt_records[0].status == "cancelled"
    assert ctx.interrupt_records[0].resume_value["allow_continue"] is False
