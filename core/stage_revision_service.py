# core/stage_revision_service.py
"""Stage revision and dependency-lineage helpers.

The service centralizes non-runtime stage advancement bookkeeping:
- record dependency versions when a stage output is generated or edited;
- mark downstream stage outputs stale when upstream stages change;
- supersede stale downstream actions;
- record audit events for revision/rollback/invalidation.

It does not run pytest, services, Docker, or external workflow execution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.audit_service import append_audit_event
from core.models import ProjectContext, SessionState


class StageMutationResult(BaseModel):
    """Non-runtime summary of a stage mutation.

    Existing revision helpers keep returning ProjectContext for backward
    compatibility. This result object is used by reports, docs, and future API
    responses to describe version lineage effects without changing the current
    execution contract.
    """

    stage_id: int
    operation: Literal["run", "edit", "revise", "rollback", "rerun", "sync_review_actions"]
    version_before: int
    version_after: int | None = None
    stale_stages: list[str] = Field(default_factory=list)
    superseded_action_ids: list[str] = Field(default_factory=list)
    audit_event_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def collect_stage_mutation_result(
    ctx: ProjectContext,
    *,
    stage: int,
    operation: Literal["run", "edit", "revise", "rollback", "rerun", "sync_review_actions"],
    version_before: int,
    version_after: int | None = None,
    stale_stages: list[str] | None = None,
    superseded_action_ids: list[str] | None = None,
    audit_event_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> StageMutationResult:
    """Build a structured mutation summary without mutating the context."""

    return StageMutationResult(
        stage_id=stage,
        operation=operation,
        version_before=version_before,
        version_after=version_after,
        stale_stages=stale_stages or [],
        superseded_action_ids=superseded_action_ids or [],
        audit_event_ids=audit_event_ids or [],
        metadata=metadata or {},
    )


def stage_key(stage: int) -> str:
    if stage < 1 or stage > 4:
        raise ValueError(f"stage must be 1..4, got {stage}")
    return f"stage_{stage}"


def current_stage_output_version(ctx: ProjectContext, stage: int) -> int:
    return int(ctx.stage_output_versions.get(stage_key(stage), 1))


def record_stage_dependency_versions(ctx: ProjectContext, stage: int) -> dict[str, int]:
    """Record upstream stage versions used by a newly generated/edited stage output."""
    key = stage_key(stage)
    dependencies = {
        stage_key(upstream): current_stage_output_version(ctx, upstream)
        for upstream in range(1, stage)
    }
    ctx.stage_dependency_versions[key] = dependencies
    # The current stage has just been regenerated/edited, so it is no longer stale.
    ctx.stage_staleness.pop(key, None)
    append_audit_event(
        ctx,
        actor="system",
        event_type="stage_dependency_versions_recorded",
        target_type="stage",
        target_id=key,
        after={"stage_dependency_versions": dependencies},
        metadata={"stage_id": stage},
    )
    return dependencies


def _downstream_has_state(ctx: ProjectContext, stage: int) -> bool:
    key = stage_key(stage)
    has_output = getattr(ctx, f"stage_{stage}_output", None) is not None
    has_dependencies = bool(ctx.stage_dependency_versions.get(key))
    has_parser_error = bool(ctx.parser_errors.get(key))
    has_actions = any(action.stage_id == stage for action in ctx.pending_actions)
    return has_output or has_dependencies or has_parser_error or has_actions


def invalidate_downstream_stages(
    ctx: ProjectContext,
    *,
    changed_stage: int,
    reason: str,
    superseded_by: str | None = None,
) -> list[str]:
    """Mark downstream stages stale after a stage output changes.

    The existing downstream output is preserved for auditability, but gate
    evaluation will block it with stale_dependency until the downstream stage is
    rerun. Pending/rejected downstream actions are superseded so old actions do
    not keep blocking a new version lineage.
    """
    if changed_stage < 1 or changed_stage > 4:
        raise ValueError(f"changed_stage must be 1..4, got {changed_stage}")

    stale_keys: list[str] = []
    now = datetime.utcnow().isoformat()
    for downstream in range(changed_stage + 1, 5):
        if not _downstream_has_state(ctx, downstream):
            continue

        key = stage_key(downstream)
        metadata = {
            "stale": True,
            "because_stage": changed_stage,
            "because_stage_key": stage_key(changed_stage),
            "reason": reason,
            "created_at": now,
            "stage_output_exists": getattr(ctx, f"stage_{downstream}_output", None) is not None,
            "dependency_versions": dict(ctx.stage_dependency_versions.get(key, {})),
            "current_upstream_versions": {
                stage_key(upstream): current_stage_output_version(ctx, upstream)
                for upstream in range(1, downstream)
            },
            "superseded_by": superseded_by,
        }
        ctx.stage_staleness[key] = metadata
        ctx.parser_errors.pop(key, None)

        # Import lazily to avoid circular import with core.oversight_service.
        from core.oversight_service import supersede_actions_for_stage

        supersede_actions_for_stage(
            ctx,
            stage=downstream,
            reason=f"Downstream stage marked stale: {reason}",
            superseded_by=superseded_by,
        )
        append_audit_event(
            ctx,
            actor="system",
            event_type="downstream_stage_marked_stale",
            target_type="stage",
            target_id=key,
            after=metadata,
            metadata={"changed_stage": changed_stage, "downstream_stage": downstream},
        )
        stale_keys.append(key)
    return stale_keys


def revise_stage(
    ctx: ProjectContext,
    *,
    stage: int,
    reason: str,
    note: str = "",
    superseded_by: str | None = None,
) -> ProjectContext:
    """Prepare the current stage for regeneration and stale downstream outputs."""
    from core.oversight_service import supersede_actions_for_stage

    running_states = {
        1: SessionState.S1_RUNNING,
        2: SessionState.S2_RUNNING,
        3: SessionState.S3_RUNNING,
        4: SessionState.S4_RUNNING,
    }
    supersede_actions_for_stage(
        ctx,
        stage=stage,
        reason=reason,
        superseded_by=superseded_by,
    )
    invalidate_downstream_stages(
        ctx,
        changed_stage=stage,
        reason=reason,
        superseded_by=superseded_by,
    )
    ctx.current_state = running_states[stage]
    ctx.review_notes[f"stage_{stage}"] = f"revise: {note}".strip()
    ctx.iteration_count += 1
    append_audit_event(
        ctx,
        actor="user",
        event_type="stage_revision_requested",
        target_type="stage",
        target_id=stage_key(stage),
        after={"current_state": ctx.current_state.value, "note": note},
        metadata={"stage_id": stage, "reason": reason},
    )
    return ctx


def rollback_stage(
    ctx: ProjectContext,
    *,
    from_stage: int,
    to_stage: int,
    reason: str,
    target_running: bool = False,
    superseded_by: str | None = None,
) -> ProjectContext:
    """Rollback to an earlier stage and invalidate outputs after that stage."""
    if to_stage < 0 or to_stage >= from_stage:
        raise ValueError(
            f"rollback requires 0 <= to_stage < from_stage, got {to_stage} -> {from_stage}"
        )

    from core.oversight_service import supersede_actions_for_stage

    for stage in range(to_stage + 1, from_stage + 1):
        supersede_actions_for_stage(
            ctx,
            stage=stage,
            reason=reason,
            superseded_by=superseded_by,
        )

    if to_stage >= 1:
        invalidate_downstream_stages(
            ctx,
            changed_stage=to_stage,
            reason=reason,
            superseded_by=superseded_by,
        )

    if to_stage == 0:
        ctx.current_state = SessionState.INIT
    elif target_running:
        ctx.current_state = {
            1: SessionState.S1_RUNNING,
            2: SessionState.S2_RUNNING,
            3: SessionState.S3_RUNNING,
            4: SessionState.S4_RUNNING,
        }[to_stage]
    else:
        ctx.current_state = {
            1: SessionState.S1_REVIEW,
            2: SessionState.S2_REVIEW,
            3: SessionState.S3_REVIEW,
            4: SessionState.S4_REVIEW,
        }[to_stage]

    ctx.iteration_count = 0
    append_audit_event(
        ctx,
        actor="user",
        event_type="stage_rollback_requested",
        target_type="stage",
        target_id=stage_key(from_stage),
        after={"current_state": ctx.current_state.value},
        metadata={"from_stage": from_stage, "to_stage": to_stage, "reason": reason},
    )
    return ctx
