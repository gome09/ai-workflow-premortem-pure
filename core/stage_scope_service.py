# core/stage_scope_service.py
"""Stage visibility and actionability helpers for v0.6.0-alpha.7.

This module is intentionally read-only. It keeps future-stage placeholders out
of the current resolution queue so StageResolutionOperation only tells users
about stages that are actually reachable/actionable in the current workflow
state. It does not run stages, mutate context, or perform validation.
"""

from __future__ import annotations

from typing import Any

from core.models import ProjectContext

_STATE_TO_STAGE: dict[str, int] = {
    "init": 1,
    "s1_running": 1,
    "s1_review": 1,
    "s2_running": 2,
    "s2_review": 2,
    "s3_running": 3,
    "s3_review": 3,
    "s4_running": 4,
    "s4_review": 4,
    "iterating": 4,
    "complete": 4,
}


def _state_value(ctx: ProjectContext) -> str:
    return getattr(ctx.current_state, "value", str(ctx.current_state))


def current_stage_id(ctx: ProjectContext) -> int:
    """Return the stage currently responsible for user-facing advancement.

    INIT still maps to stage 1 because the first actionable operation is to run
    Stage 1. Unknown states fall back to the highest generated output stage, or
    Stage 1 when no outputs exist.
    """
    state_stage = _STATE_TO_STAGE.get(_state_value(ctx))
    if state_stage is not None:
        return state_stage
    generated = [
        stage for stage in range(1, 5) if getattr(ctx, f"stage_{stage}_output", None) is not None
    ]
    return max(generated) if generated else 1


def reached_stage_ids(ctx: ProjectContext) -> list[int]:
    """Stages that have been reached by state or by an existing stage output."""
    max_reached = current_stage_id(ctx)
    for stage in range(1, 5):
        if getattr(ctx, f"stage_{stage}_output", None) is not None:
            max_reached = max(max_reached, stage)
    return list(range(1, max_reached + 1))


def actionable_stage_ids(ctx: ProjectContext) -> list[int]:
    """Stages that may legitimately contribute current blockers/operations.

    This intentionally excludes future not-started stages so their
    missing_stage_output blockers do not pollute the current next-step queue.
    """
    return reached_stage_ids(ctx)


def is_stage_actionable(ctx: ProjectContext, stage: int) -> bool:
    return stage in set(actionable_stage_ids(ctx))


def future_stage_placeholders(ctx: ProjectContext) -> list[dict[str, Any]]:
    actionables = set(actionable_stage_ids(ctx))
    return [
        {
            "stage_id": stage,
            "stage_key": f"stage_{stage}",
            "stage_lifecycle": "not_started",
            "reason": "future_stage_not_reached",
            "message": "Future stage is not reached yet; its missing output is not a current blocker.",
        }
        for stage in range(1, 5)
        if stage not in actionables
    ]
