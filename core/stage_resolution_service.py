# core/stage_resolution_service.py
"""Stage resolution operations.

StageReadiness answers: "can this stage advance?"
StageResolutionOperation answers: "what exact user operation can resolve each blocker?"

This module is intentionally non-executing. It does not run stages, resolve
actions, verify evidence, call external services, or start runtime validation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.models import ProjectContext
from core.stage_advancement_contract import operation_contract_for
from core.stage_readiness_service import evaluate_stage_gate
from core.stage_scope_service import (
    actionable_stage_ids,
    current_stage_id,
    future_stage_placeholders,
)


class StageResolutionOperation(BaseModel):
    """User-facing operation derived from one StageBlocker."""

    operation_id: str
    stage_id: int
    stage_output_version: int
    blocker_id: str
    blocker_type: str
    required_resolution: str
    severity: str
    source_type: str | None = None
    source_id: str | None = None
    action_id: str | None = None
    api_hint: str
    frontend_hint: str
    can_execute_via_api: bool = False
    api_method: str | None = None
    api_path_template: str | None = None
    api_path: str | None = None
    payload_hint: dict[str, Any] = Field(default_factory=dict)
    hard_blocker: bool = True
    can_be_overridden_by_approval: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def _safe_token(value: str | None) -> str:
    import re

    token = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "none").strip("_")
    return token[:100] or "none"


def _api_path(
    *,
    session_id: str,
    required_resolution: str,
    source_type: str | None,
    source_id: str | None,
    action_id: str | None,
    stage_id: int | None,
    template: str | None,
) -> str | None:
    if not template:
        return None

    if "{action_id}" in template:
        if not action_id:
            return None
        return template.format(session_id=session_id, action_id=action_id)

    if "{evidence_id}" in template:
        if source_type != "evidence" or not source_id:
            return None
        return template.format(session_id=session_id, evidence_id=source_id)

    if "{finding_id}" in template:
        if source_type != "safety_finding" or not source_id:
            return None
        return template.format(session_id=session_id, finding_id=source_id)

    if "{experiment_id}" in template:
        if source_type != "eval_experiment" or not source_id:
            return None
        return template.format(session_id=session_id, experiment_id=source_id)

    if "{dataset_id}" in template:
        if source_type != "eval_dataset" or not source_id:
            return None
        return template.format(session_id=session_id, dataset_id=source_id)

    if "{case_id}" in template:
        if source_type != "redteam_case" or not source_id:
            return None
        return template.format(session_id=session_id, case_id=source_id)

    if "{trace_id}" in template:
        if source_type != "trace" or not source_id:
            return None
        return template.format(session_id=session_id, trace_id=source_id)

    if "{stage_id}" in template:
        if stage_id is None:
            return None
        return template.format(session_id=session_id, stage_id=stage_id)

    # Keep the explicit resolution check so future templates cannot accidentally
    # look executable without a verified source binding.
    if (
        required_resolution in {"resolve_action", "approve_escalation", "edit_stage_output"}
        and not action_id
    ):
        return None

    return template.format(session_id=session_id)


def _operation_from_blocker(ctx: ProjectContext, blocker: Any) -> StageResolutionOperation:
    contract = operation_contract_for(str(blocker.required_resolution))
    api_template = contract.get("api_path_template")
    api_path = _api_path(
        session_id=ctx.session_id,
        required_resolution=str(blocker.required_resolution),
        source_type=blocker.source_type,
        source_id=blocker.source_id,
        action_id=blocker.action_id,
        stage_id=blocker.stage_id,
        template=str(api_template) if api_template else None,
    )

    # A contract can be API-capable in general, but a concrete blocker is only
    # executable when its action/evidence/finding id is known.
    can_execute = bool(contract.get("can_execute_via_api")) and bool(api_path)

    operation_id = _safe_token(
        f"S{blocker.stage_id}_V{blocker.stage_output_version}_"
        f"{blocker.required_resolution}_{blocker.action_id or blocker.source_id or blocker.blocker_id}"
    )

    hard_blocker = not bool(blocker.can_be_overridden_by_approval)

    return StageResolutionOperation(
        operation_id=operation_id,
        stage_id=blocker.stage_id,
        stage_output_version=blocker.stage_output_version,
        blocker_id=blocker.blocker_id,
        blocker_type=blocker.blocker_type,
        required_resolution=blocker.required_resolution,
        severity=blocker.severity,
        source_type=blocker.source_type,
        source_id=blocker.source_id,
        action_id=blocker.action_id,
        api_hint=str(contract.get("api_hint", "")),
        frontend_hint=str(contract.get("frontend_hint", "")),
        can_execute_via_api=can_execute,
        api_method=str(contract["api_method"]) if contract.get("api_method") else None,
        api_path_template=str(api_template) if api_template else None,
        api_path=api_path,
        payload_hint=dict(contract.get("payload_hint") or {}),
        hard_blocker=hard_blocker,
        can_be_overridden_by_approval=bool(blocker.can_be_overridden_by_approval),
        metadata={
            "blocker_message": blocker.message,
            "blocker_metadata": dict(getattr(blocker, "metadata", {}) or {}),
            "api_binding_available": bool(api_path),
            "contract_api_capable": bool(contract.get("can_execute_via_api")),
        },
    )


def build_stage_resolution_operations(
    ctx: ProjectContext, stage: int
) -> list[StageResolutionOperation]:
    """Build concrete resolution operations for one stage's current blockers."""
    result = evaluate_stage_gate(ctx, stage)
    operations: list[StageResolutionOperation] = []
    seen: set[str] = set()
    for blocker in result.blockers:
        operation = _operation_from_blocker(ctx, blocker)
        if operation.operation_id in seen:
            continue
        seen.add(operation.operation_id)
        operations.append(operation)
    return operations


def build_all_stage_resolution_operations(
    ctx: ProjectContext,
    *,
    include_future: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Build concrete resolution operations by stage.

    Future not-started stages are returned with empty operation lists unless
    include_future=True. This keeps Stage 2/3/4 missing_output placeholders out
    of the current next-step queue while preserving stable stage keys for API
    and frontend consumers.
    """
    active = set(range(1, 5) if include_future else actionable_stage_ids(ctx))
    return {
        f"stage_{stage}": [
            operation.model_dump(mode="json")
            for operation in build_stage_resolution_operations(ctx, stage)
        ]
        if stage in active
        else []
        for stage in range(1, 5)
    }


def build_stage_resolution_summary(ctx: ProjectContext) -> dict[str, Any]:
    """Compact summary for API, report export, and frontend sidebar."""
    actionables = actionable_stage_ids(ctx)
    by_stage = build_all_stage_resolution_operations(ctx, include_future=False)
    current_operations = [
        operation for stage in actionables for operation in by_stage.get(f"stage_{stage}", [])
    ]
    hard_blockers = [op for op in current_operations if op.get("hard_blocker")]
    overridable_blockers = [
        op for op in current_operations if op.get("can_be_overridden_by_approval")
    ]
    executable_operations = [op for op in current_operations if op.get("can_execute_via_api")]

    return {
        "by_stage": by_stage,
        "current_stage_id": current_stage_id(ctx),
        "actionable_stage_ids": actionables,
        "future_stage_placeholders": future_stage_placeholders(ctx),
        "total_operations": len(current_operations),
        "hard_blockers_count": len(hard_blockers),
        "overridable_blockers_count": len(overridable_blockers),
        "executable_operations_count": len(executable_operations),
        "hard_blockers": hard_blockers,
        "overridable_blockers": overridable_blockers,
        "current_required_operations": current_operations,
    }


def get_next_required_operation(
    ctx: ProjectContext, stage: int | None = None
) -> dict[str, Any] | None:
    """Return the first hard blocker operation, falling back to any blocker operation."""
    candidate_stages = [stage] if stage is not None else actionable_stage_ids(ctx)
    operations: list[dict[str, Any]] = []
    for candidate_stage in candidate_stages:
        operations.extend(
            operation.model_dump(mode="json")
            for operation in build_stage_resolution_operations(ctx, candidate_stage)
        )

    for operation in operations:
        if operation.get("hard_blocker"):
            return operation
    return operations[0] if operations else None
