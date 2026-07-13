# core/stage_operation_service.py
"""Executable stage-operation helpers for the stage-advancement contract.

This module closes the existing stage-advancement loop without redesigning the
project. It does not call LLMs, pytest, Streamlit, Docker, Tavily, or any
external runtime. It only prepares already-supported stage state transitions:
rerun, revise, rollback, and explicit review-action synchronization.

The stable execution path remains deterministic single_step. LangGraph
interrupt/checkpoint support stays experimental and is coordinated by
core.execution_service after these business mutations are persisted.
"""

from __future__ import annotations

from typing import Any

from core.audit_service import append_audit_event
from core.models import HumanActionStatus, ProjectContext
from core.oversight_service import create_review_actions_for_stage
from core.stage_revision_service import (
    StageMutationResult,
    collect_stage_mutation_result,
    current_stage_output_version,
    revise_stage,
    rollback_stage,
    stage_key,
)


def _validate_stage(stage: int) -> None:
    if stage < 1 or stage > 4:
        raise ValueError(f"stage must be 1..4, got {stage}")


def _action_status_snapshot(ctx: ProjectContext) -> dict[str, str]:
    return {action.action_id: str(action.status) for action in ctx.pending_actions}


def _newly_superseded_action_ids(ctx: ProjectContext, before: dict[str, str]) -> list[str]:
    return [
        action.action_id
        for action in ctx.pending_actions
        if before.get(action.action_id) != HumanActionStatus.SUPERSEDED.value
        and action.status == HumanActionStatus.SUPERSEDED.value
    ]


def _stale_stage_keys(ctx: ProjectContext) -> list[str]:
    return [
        key
        for key, value in getattr(ctx, "stage_staleness", {}).items()
        if isinstance(value, dict) and value.get("stale")
    ]


def prepare_stage_rerun(
    ctx: ProjectContext,
    *,
    stage: int,
    reason: str = "",
    note: str = "",
) -> StageMutationResult:
    """Prepare a stale or rejected stage for rerun without executing the stage."""

    _validate_stage(stage)
    before_version = current_stage_output_version(ctx, stage)
    before_actions = _action_status_snapshot(ctx)
    reason = reason or f"Stage {stage} rerun requested through stage operation API."
    revise_stage(ctx, stage=stage, reason=reason, note=note, superseded_by=f"stage_{stage}_rerun")
    return collect_stage_mutation_result(
        ctx,
        stage=stage,
        operation="rerun",
        version_before=before_version,
        version_after=current_stage_output_version(ctx, stage),
        stale_stages=_stale_stage_keys(ctx),
        superseded_action_ids=_newly_superseded_action_ids(ctx, before_actions),
        metadata={
            "reason": reason,
            "note": note,
            "current_state": ctx.current_state.value,
            "next_step": "Send project input through POST /chat/{session_id} to regenerate the stage.",
            "does_not_call_llm": True,
        },
    )


def request_stage_revision(
    ctx: ProjectContext,
    *,
    stage: int,
    reason: str = "",
    note: str = "",
) -> StageMutationResult:
    """Prepare the current stage for human-requested revision."""

    _validate_stage(stage)
    before_version = current_stage_output_version(ctx, stage)
    before_actions = _action_status_snapshot(ctx)
    reason = reason or f"Stage {stage} revision requested through stage operation API."
    revise_stage(
        ctx, stage=stage, reason=reason, note=note, superseded_by=f"stage_{stage}_revision"
    )
    return collect_stage_mutation_result(
        ctx,
        stage=stage,
        operation="revise",
        version_before=before_version,
        version_after=current_stage_output_version(ctx, stage),
        stale_stages=_stale_stage_keys(ctx),
        superseded_action_ids=_newly_superseded_action_ids(ctx, before_actions),
        metadata={
            "reason": reason,
            "note": note,
            "current_state": ctx.current_state.value,
            "next_step": "Send revised input through POST /chat/{session_id}.",
            "does_not_call_llm": True,
        },
    )


def request_stage_rollback(
    ctx: ProjectContext,
    *,
    from_stage: int,
    to_stage: int,
    reason: str = "",
    note: str = "",
    target_running: bool = False,
) -> StageMutationResult:
    """Rollback from the current/later stage to an earlier stage."""

    _validate_stage(from_stage)
    if to_stage < 0 or to_stage >= from_stage:
        raise ValueError(
            f"rollback requires 0 <= to_stage < from_stage, got {to_stage} -> {from_stage}"
        )

    before_version = current_stage_output_version(ctx, from_stage)
    before_actions = _action_status_snapshot(ctx)
    reason = (
        reason
        or f"Rollback from stage {from_stage} to stage {to_stage} requested through stage operation API."
    )
    rollback_stage(
        ctx,
        from_stage=from_stage,
        to_stage=to_stage,
        reason=reason,
        target_running=target_running,
        superseded_by=f"stage_{from_stage}_rollback_to_{to_stage}",
    )
    if note:
        ctx.review_notes[f"stage_{from_stage}_rollback"] = note

    return collect_stage_mutation_result(
        ctx,
        stage=from_stage,
        operation="rollback",
        version_before=before_version,
        version_after=current_stage_output_version(ctx, from_stage),
        stale_stages=_stale_stage_keys(ctx),
        superseded_action_ids=_newly_superseded_action_ids(ctx, before_actions),
        metadata={
            "reason": reason,
            "note": note,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "target_running": target_running,
            "current_state": ctx.current_state.value,
            "does_not_call_llm": True,
        },
    )


def sync_stage_review_actions(
    ctx: ProjectContext,
    *,
    stage: int,
    reason: str = "manual_sync_review_actions",
) -> StageMutationResult:
    """Regenerate missing PendingHumanAction records for current gate blockers."""

    _validate_stage(stage)
    before_count = len(ctx.pending_actions)
    created = create_review_actions_for_stage(
        ctx,
        stage,
        stage_output_version=current_stage_output_version(ctx, stage),
    )
    event = append_audit_event(
        ctx,
        actor="system",
        event_type="stage_review_actions_synced",
        target_type="stage",
        target_id=stage_key(stage),
        after={
            "pending_actions_count_before": before_count,
            "pending_actions_count_after": len(ctx.pending_actions),
            "created_count": len(created),
        },
        metadata={
            "stage_id": stage,
            "reason": reason,
            "stage_output_version": current_stage_output_version(ctx, stage),
        },
    )
    return collect_stage_mutation_result(
        ctx,
        stage=stage,
        operation="sync_review_actions",
        version_before=current_stage_output_version(ctx, stage),
        version_after=current_stage_output_version(ctx, stage),
        stale_stages=_stale_stage_keys(ctx),
        audit_event_ids=[event.event_id],
        metadata={
            "reason": reason,
            "created_count": len(created),
            "pending_actions_count_before": before_count,
            "pending_actions_count_after": len(ctx.pending_actions),
            "does_not_advance_stage": True,
        },
    )


def stage_operation_payload(result: StageMutationResult) -> dict[str, Any]:
    return {
        "mutation": result.model_dump(mode="json"),
        "runtime_validation": "deferred_by_instruction",
    }
