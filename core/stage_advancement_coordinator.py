# core/stage_advancement_coordinator.py
"""Coordination helpers for the v0.8.0-alpha.10 stage advancement contract-closure pass.

The coordinator composes existing project services:
- GateEngine / StageGateResult;
- StageResolutionOperation;
- PendingHumanAction execution sync;
- Stage mutation summaries;
- lightweight trace records.

It intentionally does not run pytest, API startup, Streamlit startup, Docker,
LLM calls, search calls, or any v0.9 feature work. Alpha.10 closes the
existing v0.8 stage-advancement path.
"""

from __future__ import annotations

from typing import Any

from core.audit_service import append_audit_event
from core.models import ProjectContext, SessionState
from core.stage_advancement_decision import (
    DecisionSource,
    StageAdvancementDecision,
    StageOperationEnvelope,
)
from core.stage_readiness_service import _stage_lifecycle, evaluate_stage_gate
from core.stage_resolution_service import (
    build_stage_resolution_operations,
    get_next_required_operation,
)
from core.stage_scope_service import current_stage_id
from core.traces import append_llm_trace, create_llm_trace

_NEXT_STATES = {
    1: SessionState.S2_RUNNING,
    2: SessionState.S3_RUNNING,
    3: SessionState.S4_RUNNING,
    4: SessionState.COMPLETE,
}


def _state_value(ctx: ProjectContext) -> str:
    return getattr(ctx.current_state, "value", str(ctx.current_state))


def _stale_stage_keys(ctx: ProjectContext) -> list[str]:
    return [
        key
        for key, value in getattr(ctx, "stage_staleness", {}).items()
        if isinstance(value, dict) and value.get("stale")
    ]


def _infer_stage_from_actions(ctx: ProjectContext, action_ids: list[str]) -> int | None:
    action_id_set = set(action_ids)
    for action in getattr(ctx, "pending_actions", []) or []:
        if action.action_id in action_id_set:
            return action.stage_id
    return None


def _safe_stage(
    ctx: ProjectContext, stage: int | None = None, action_ids: list[str] | None = None
) -> int:
    candidate = stage or _infer_stage_from_actions(ctx, action_ids or []) or current_stage_id(ctx)
    if candidate is None or candidate < 1:
        return 1
    if candidate > 4:
        return 4
    return int(candidate)


def _rules_evaluated(gate_result) -> list[str]:
    return list(getattr(gate_result, "_rules_evaluated", []) or [])


def _trace_decision(
    ctx: ProjectContext,
    decision: StageAdvancementDecision,
    *,
    trace_type: str = "gate",
    node_name: str = "stage_advancement_decision",
    extra_metadata: dict[str, Any] | None = None,
):
    metadata = {
        "event_kind": "stage_advancement_decision",
        "decision_source": decision.decision_source,
        "decision_reason": decision.decision_reason,
        "stage_lifecycle": decision.stage_lifecycle,
        "can_advance": decision.can_advance,
        "advanced": decision.advanced,
        "next_state": decision.next_state,
        "blockers_count": len(decision.gate_result.blockers),
        "blocker_ids": [item.blocker_id for item in decision.gate_result.blockers],
        "blocker_rule_ids": [item.rule_id for item in decision.gate_result.blockers],
        "required_operation_ids": [item.operation_id for item in decision.required_operations],
        "blocking_action_ids": decision.blocking_action_ids,
        "stale_stage_keys": decision.stale_stage_keys,
        "runtime_validation": decision.runtime_validation,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    trace = create_llm_trace(
        ctx,
        stage=decision.stage_id,
        node_name=node_name,
        trace_type=trace_type,
        parser_status="not_applicable",
        metadata=metadata,
    )
    append_llm_trace(ctx, trace)
    decision.trace_id = trace.trace_id
    return trace


def append_action_resolution_trace(
    ctx: ProjectContext,
    *,
    action_ids: list[str],
    result_status: str,
    source: str,
    stage: int | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Record action-resolution outcomes even when they do not advance the stage."""

    safe_stage = _safe_stage(ctx, stage=stage, action_ids=action_ids)
    trace = create_llm_trace(
        ctx,
        stage=safe_stage,
        node_name=source,
        trace_type="action",
        parser_status="not_applicable",
        metadata={
            "event_kind": "action_resolution",
            "action_ids": action_ids,
            "result_status": result_status,
            "source": source,
            **(metadata or {}),
        },
    )
    return append_llm_trace(ctx, trace)


def build_stage_advancement_decision(
    ctx: ProjectContext,
    stage: int,
    *,
    decision_source: DecisionSource = "stage_gate",
    reason: str = "",
    append_trace: bool = False,
    trace_type: str = "gate",
    node_name: str = "stage_advancement_decision",
    metadata: dict[str, Any] | None = None,
) -> StageAdvancementDecision:
    """Build a non-mutating authoritative stage-advancement decision."""

    if stage < 1 or stage > 4:
        raise ValueError(f"stage must be 1..4, got {stage}")

    gate_result = evaluate_stage_gate(ctx, stage)
    operations = build_stage_resolution_operations(ctx, stage)
    hard_operations = [op for op in operations if op.hard_blocker]
    overridable_operations = [op for op in operations if op.can_be_overridden_by_approval]
    executable_operations = [op for op in operations if op.can_execute_via_api]
    blockers = list(gate_result.blockers)
    lifecycle = _stage_lifecycle(ctx, stage, gate_result)
    next_state = _NEXT_STATES[stage].value if gate_result.can_continue else None
    decision_reason = reason or (
        "gate_clear_ready_to_advance" if gate_result.can_continue else "blocked_by_stage_gate"
    )

    decision = StageAdvancementDecision(
        session_id=ctx.session_id,
        stage_id=stage,
        stage_output_version=gate_result.stage_output_version,
        current_state=_state_value(ctx),
        stage_lifecycle=lifecycle,
        can_advance=gate_result.can_continue,
        advanced=False,
        next_state=next_state,
        gate_result=gate_result,
        required_operations=operations,
        blocking_action_ids=[blocker.action_id for blocker in blockers if blocker.action_id],
        stale_stage_keys=_stale_stage_keys(ctx),
        decision_reason=decision_reason,
        decision_source=decision_source,
        rules_evaluated=_rules_evaluated(gate_result),
        hard_blockers_count=len(hard_operations),
        overridable_blockers_count=len(overridable_operations),
        executable_operations_count=len(executable_operations),
        metadata=metadata or {},
    )
    if append_trace:
        _trace_decision(
            ctx,
            decision,
            trace_type=trace_type,
            node_name=node_name,
            extra_metadata=metadata,
        )
    return decision


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def build_stage_operation_envelope(
    ctx: ProjectContext,
    *,
    operation: str,
    result: Any,
    stage: int | None = None,
    source: DecisionSource = "system",
    reason: str = "",
    append_trace: bool = True,
    metadata: dict[str, Any] | None = None,
) -> StageOperationEnvelope:
    """Wrap a mutating operation result with the latest advancement decision.

    This is the alpha.10 coordination contract: every operation that can change a
    stage gate returns its own domain result plus a refreshed
    StageAdvancementDecision and the next concrete required operation.
    """
    safe_stage = _safe_stage(ctx, stage=stage)
    result_payload = _jsonable(result)
    decision = build_stage_advancement_decision(
        ctx,
        safe_stage,
        decision_source=source,
        reason=reason or operation,
        append_trace=append_trace,
        trace_type="stage_operation",
        node_name=f"post_{operation}_gate",
        metadata={
            "event_kind": operation,
            "operation": operation,
            "runtime_validation": "deferred_by_instruction",
            **(metadata or {}),
        },
    )
    return StageOperationEnvelope(
        session_id=ctx.session_id,
        operation=operation,
        result=result_payload,
        result_type=type(result).__name__,
        stage_id=safe_stage,
        stage_advancement_decision=decision,
        next_required_operation=get_next_required_operation(ctx, safe_stage),
        metadata={
            "operation_source": source,
            "reason": reason or operation,
            "runtime_validation": "deferred_by_instruction",
            **(metadata or {}),
        },
    )


def advance_stage_if_ready(
    ctx: ProjectContext,
    stage: int,
    *,
    reason: str = "",
    source: DecisionSource = "api_advance",
) -> StageAdvancementDecision:
    """Mutate current_state only when the authoritative gate allows advancement."""

    decision = build_stage_advancement_decision(
        ctx,
        stage,
        decision_source=source,
        reason=reason,
        append_trace=True,
        trace_type="gate",
        node_name="stage_advance_gate",
    )
    if not decision.can_advance:
        decision.decision_reason = reason or "stage_advance_blocked_by_gate"
        _trace_decision(
            ctx,
            decision,
            trace_type="stage_operation",
            node_name="stage_advance_blocked",
            extra_metadata={"event_kind": "stage_advance_blocked"},
        )
        return decision

    next_state = _NEXT_STATES[stage]
    ctx.current_state = next_state
    ctx.review_notes[f"stage_{stage}"] = "approved"
    decision.advanced = True
    decision.current_state = next_state.value
    decision.next_state = next_state.value
    decision.decision_reason = reason or "stage_advanced"

    event = append_audit_event(
        ctx,
        actor="system",
        event_type="stage_advanced",
        target_type="stage",
        target_id=f"stage_{stage}",
        after={
            "current_state": next_state.value,
            "stage_output_version": decision.stage_output_version,
            "next_state": next_state.value,
        },
        metadata={
            "stage_id": stage,
            "decision_source": source,
            "required_operations_count": len(decision.required_operations),
            "runtime_validation": decision.runtime_validation,
        },
    )
    _trace_decision(
        ctx,
        decision,
        trace_type="stage_operation",
        node_name="stage_advanced",
        extra_metadata={
            "event_kind": "stage_advanced",
            "audit_event_id": event.event_id,
        },
    )
    return decision


def after_human_resolution(
    ctx: ProjectContext,
    *,
    action_ids: list[str],
    reason: str,
    source: DecisionSource = "action_resolution",
    stage: int | None = None,
) -> tuple[ProjectContext, StageAdvancementDecision]:
    """Synchronize execution state after human work and refresh advancement decision."""

    from core.execution_service import sync_execution_after_action_resolutions

    ctx = sync_execution_after_action_resolutions(ctx, action_ids, reason=reason)
    safe_stage = _safe_stage(ctx, stage=stage, action_ids=action_ids)
    append_action_resolution_trace(
        ctx,
        action_ids=action_ids,
        result_status="resolved",
        source=source,
        stage=safe_stage,
        metadata={"reason": reason},
    )
    decision = build_stage_advancement_decision(
        ctx,
        safe_stage,
        decision_source=source,
        reason=reason or "human_resolution_synced",
        append_trace=True,
        trace_type="gate",
        node_name="post_human_resolution_gate",
    )
    return ctx, decision


def after_stage_mutation(
    ctx: ProjectContext,
    mutation_result,
    *,
    reason: str,
    source: DecisionSource,
) -> StageAdvancementDecision:
    """Record a stage-operation trace and refresh the gate decision after mutation."""

    stage = int(getattr(mutation_result, "stage_id", None) or current_stage_id(ctx) or 1)
    trace = create_llm_trace(
        ctx,
        stage=stage,
        node_name=source,
        trace_type="stage_operation",
        parser_status="not_applicable",
        metadata={
            "event_kind": source,
            "reason": reason,
            "mutation": mutation_result.model_dump(mode="json")
            if hasattr(mutation_result, "model_dump")
            else {},
            "runtime_validation": "deferred_by_instruction",
        },
    )
    append_llm_trace(ctx, trace)
    return build_stage_advancement_decision(
        ctx,
        stage,
        decision_source=source,
        reason=reason or source,
        append_trace=True,
        trace_type="gate",
        node_name=f"post_{source}_gate",
    )
