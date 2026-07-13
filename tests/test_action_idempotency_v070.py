"""v0.7 action idempotency contract tests for the later unified validation pass."""

from __future__ import annotations

from core.models import PendingHumanAction, ProjectContext
from core.oversight_service import resolve_action_with_result


def test_duplicate_action_resolution_returns_idempotent_replay():
    ctx = ProjectContext()
    action = PendingHumanAction(
        session_id=ctx.session_id,
        stage_id=1,
        source_type="parser",
        source_id="stage_1",
        action_type="approve",
        title="Approve parser action",
        description="Fixture",
        target_object_path="stage_1.parser.stage_1",
        stage_output_version=1,
    )
    ctx.pending_actions.append(action)

    first = resolve_action_with_result(
        ctx,
        action_id=action.action_id,
        decision="approve",
        idempotency_key="idem-1",
    )
    second = resolve_action_with_result(
        ctx,
        action_id=action.action_id,
        decision="approve",
        idempotency_key="idem-1",
    )

    assert first.result_status == "resolved"
    assert second.result_status == "idempotent_replay"


def test_stale_action_resolution_is_explicit():
    ctx = ProjectContext(stage_output_versions={"stage_1": 2})
    action = PendingHumanAction(
        session_id=ctx.session_id,
        stage_id=1,
        source_type="parser",
        source_id="stage_1",
        action_type="approve",
        title="Approve stale action",
        description="Fixture",
        target_object_path="stage_1.parser.stage_1",
        stage_output_version=1,
    )
    ctx.pending_actions.append(action)

    result = resolve_action_with_result(ctx, action_id=action.action_id, decision="approve")

    assert result.result_status == "stale"
    assert action.status == "stale"
