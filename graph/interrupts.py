# graph/interrupts.py
from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from core.audit_service import append_audit_event
from core.models import HumanActionStatus, InterruptRecord, ProjectContext


def _policy_effect_dump(policy_effect: Any | None) -> dict[str, Any]:
    """Serialize ActionResolutionEffect without importing oversight policy types."""
    if policy_effect is None:
        return {
            "allow_continue": None,
            "require_revision": None,
            "require_escalation": None,
            "policy_message": "",
        }
    return {
        "allow_continue": getattr(policy_effect, "allow_continue", None),
        "require_revision": getattr(policy_effect, "require_revision", None),
        "require_escalation": getattr(policy_effect, "require_escalation", None),
        "policy_message": getattr(policy_effect, "message", ""),
    }


def _node_name_for_action(action: Any) -> str:
    if action.node_id:
        return cast(str, action.node_id)
    return f"stage_{action.stage_id}_review_gate"


def _default_thread_id(ctx: ProjectContext) -> str:
    """Use session_id as the stable LangGraph thread_id for this adapter stage."""
    return ctx.session_id


def _action_allows_resume(action: Any, policy_effect: Any | None = None) -> bool:
    if policy_effect is not None:
        return bool(getattr(policy_effect, "allow_continue", False))
    if action.status != HumanActionStatus.RESOLVED.value:
        return False
    if action.reviewer_decision == "reject":
        return False
    return True


def _resume_value_for_action(action: Any, policy_effect: Any | None = None) -> dict[str, Any]:
    policy = _policy_effect_dump(policy_effect)
    return {
        "action_id": action.action_id,
        "decision": action.reviewer_decision,
        "note": action.reviewer_note,
        "status": action.status,
        "payload_after": action.payload_after,
        "stage_id": action.stage_id,
        "stage_output_version": action.stage_output_version,
        **policy,
    }


def build_interrupt_payload(
    ctx: ProjectContext, record_or_action: InterruptRecord | Any
) -> dict[str, Any]:
    """Build the stable payload exposed by the future LangGraph interrupt call.

    The payload intentionally stays product-level: API/front-end callers should
    reason about action_id and stage state, not LangGraph internals.
    """
    action_id = getattr(record_or_action, "action_id", "")
    action = next((item for item in ctx.pending_actions if item.action_id == action_id), None)
    record = next((item for item in ctx.interrupt_records if item.action_id == action_id), None)

    stage_id = getattr(record_or_action, "stage_id", getattr(action, "stage_id", 0))
    version = getattr(
        record_or_action, "stage_output_version", getattr(action, "stage_output_version", 1)
    )
    return {
        "interrupt_id": getattr(record, "interrupt_id", None),
        "action_id": action_id,
        "session_id": ctx.session_id,
        "thread_id": getattr(record, "thread_id", None) or _default_thread_id(ctx),
        "node_name": getattr(record, "node_name", None)
        or (_node_name_for_action(action) if action else None),
        "stage_id": stage_id,
        "stage_output_version": version,
        "action_type": getattr(action, "action_type", None),
        "risk_level": getattr(action, "risk_level", None),
        "blocking": getattr(action, "blocking", None),
        "title": getattr(action, "title", ""),
        "description": getattr(action, "description", ""),
        "trigger_reason": getattr(action, "trigger_reason", ""),
        "payload_before": getattr(action, "payload_before", {}) or {},
    }


def _ensure_record_for_action(ctx: ProjectContext, action: Any) -> InterruptRecord | None:
    if not action.blocking:
        return None
    record = next(
        (item for item in ctx.interrupt_records if item.action_id == action.action_id), None
    )
    if record is None:
        record = InterruptRecord(
            session_id=ctx.session_id,
            action_id=action.action_id,
            stage_id=action.stage_id,
            stage_output_version=action.stage_output_version,
            thread_id=_default_thread_id(ctx),
            node_name=_node_name_for_action(action),
        )
        ctx.interrupt_records.append(record)
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_record_created",
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            after=record,
            metadata={
                "action_id": action.action_id,
                "stage_id": action.stage_id,
                "stage_output_version": action.stage_output_version,
            },
        )
    else:
        record.thread_id = record.thread_id or _default_thread_id(ctx)
        record.node_name = record.node_name or _node_name_for_action(action)
        record.stage_id = action.stage_id
        record.stage_output_version = action.stage_output_version

    record.interrupt_payload = build_interrupt_payload(ctx, record)
    return record


def sync_interrupt_records(ctx: ProjectContext) -> list[InterruptRecord]:
    """Keep blocking PendingHumanAction records mapped to interrupt records.

    This sync function is deliberately conservative:
    - pending blocking actions become pending InterruptRecords;
    - superseded/cancelled actions cancel their records;
    - resolved reject decisions cancel records instead of resuming the flow.
    """
    created: list[InterruptRecord] = []
    existing_ids = {record.action_id for record in ctx.interrupt_records}

    for action in ctx.pending_actions:
        if not action.blocking:
            continue

        record = _ensure_record_for_action(ctx, action)
        if record is None:
            continue
        if action.action_id not in existing_ids:
            created.append(record)
            existing_ids.add(action.action_id)

        if action.status == HumanActionStatus.PENDING.value:
            if record.status == "pending":
                record.interrupt_payload = build_interrupt_payload(ctx, record)
            continue

        if record.status != "pending":
            continue

        before = record.model_dump(mode="json")
        record.resume_value = _resume_value_for_action(action)
        record.resolved_at = datetime.utcnow()
        if _action_allows_resume(action):
            record.status = "resumed"
            event_type = "interrupt_record_resumed_from_action"
        else:
            record.status = "cancelled"
            event_type = "interrupt_record_cancelled_from_action"

        append_audit_event(
            ctx,
            actor="system",
            event_type=event_type,
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            before=before,
            after=record,
            metadata={"action_id": action.action_id, "action_status": action.status},
        )

    return created


def get_pending_blocking_interrupt(ctx: ProjectContext) -> InterruptRecord | None:
    """Return the first pending interrupt that still maps to a pending blocking action."""
    sync_interrupt_records(ctx)
    pending_blocking_actions = {
        action.action_id
        for action in ctx.pending_actions
        if action.blocking and action.status == HumanActionStatus.PENDING.value
    }
    return next(
        (
            record
            for record in ctx.interrupt_records
            if record.status == "pending" and record.action_id in pending_blocking_actions
        ),
        None,
    )


def mark_interrupt_resumed_from_action(
    ctx: ProjectContext,
    action_id: str,
    policy_effect: Any | None = None,
) -> InterruptRecord | None:
    """Mark an action-linked interrupt as resumed when policy allows continuation."""
    action = next((item for item in ctx.pending_actions if item.action_id == action_id), None)
    if action is None or not action.blocking:
        return None

    record = _ensure_record_for_action(ctx, action)
    if record is None:
        return None

    if record.status == "pending":
        before = record.model_dump(mode="json")
        if not _action_allows_resume(action, policy_effect):
            return mark_interrupt_cancelled_from_action(
                ctx,
                action_id,
                reason="Action resolution does not allow workflow continuation.",
                policy_effect=policy_effect,
            )
        record.status = "resumed"
        record.resume_value = _resume_value_for_action(action, policy_effect)
        record.resolved_at = datetime.utcnow()
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_record_resumed_from_action",
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            before=before,
            after=record,
            metadata={
                "action_id": action.action_id,
                "action_status": action.status,
                "allow_continue": True,
            },
        )
    return record


def mark_interrupt_cancelled_from_action(
    ctx: ProjectContext,
    action_id: str,
    reason: str = "",
    policy_effect: Any | None = None,
) -> InterruptRecord | None:
    """Cancel the interrupt associated with a rejected, cancelled, or superseded action."""
    action = next((item for item in ctx.pending_actions if item.action_id == action_id), None)
    if action is None or not action.blocking:
        return None

    record = _ensure_record_for_action(ctx, action)
    if record is None:
        return None

    if record.status == "pending":
        before = record.model_dump(mode="json")
        record.status = "cancelled"
        record.resume_value = {
            **_resume_value_for_action(action, policy_effect),
            "cancel_reason": reason or action.reviewer_note or "Action cancelled or superseded.",
        }
        record.resolved_at = datetime.utcnow()
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_record_cancelled_from_action",
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            before=before,
            after=record,
            metadata={
                "action_id": action.action_id,
                "action_status": action.status,
                "allow_continue": False,
                "reason": reason,
            },
        )
    return record


def mark_interrupt_resume_consumed(
    ctx: ProjectContext, interrupt_id: str
) -> InterruptRecord | None:
    """Mark that a future LangGraph Command(resume=...) value was consumed."""
    record = next(
        (item for item in ctx.interrupt_records if item.interrupt_id == interrupt_id), None
    )
    if record is None:
        return None
    if record.resume_consumed_at is None:
        before = record.model_dump(mode="json")
        record.resume_consumed_at = datetime.utcnow()
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_resume_consumed",
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            before=before,
            after=record,
            metadata={"action_id": record.action_id},
        )
    return record


def run_with_interrupt_adapter(ctx: ProjectContext) -> ProjectContext:
    """Experimental interrupt adapter entry point.

    The implementation lives in
    graph.langgraph_interrupt_runner.invoke_one_turn_with_interrupts(). Import
    lazily here to avoid circular imports: langgraph_interrupt_runner also uses
    this module's mapping helpers.
    """
    from graph.langgraph_interrupt_runner import invoke_one_turn_with_interrupts

    return invoke_one_turn_with_interrupts(ctx)
