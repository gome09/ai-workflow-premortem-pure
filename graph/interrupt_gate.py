# graph/interrupt_gate.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.audit_service import append_audit_event
from core.models import ProjectContext
from graph.interrupts import (
    build_interrupt_payload,
    get_pending_blocking_interrupt,
    mark_interrupt_resume_consumed,
    sync_interrupt_records,
)


def _load_langgraph_interrupt() -> Any:
    # -> Any：langgraph.types.interrupt 本身类型即为 (value: Any) -> Any
    """Lazy-load LangGraph's dynamic interrupt helper.

    Keeping the import lazy preserves the stable single_step path even when the
    optional interrupt/checkpoint stack is not installed or not configured.
    """
    try:
        from langgraph.types import interrupt
    except Exception:
        return None
    return interrupt


def review_interrupt_gate(ctx: ProjectContext) -> ProjectContext:
    """Pause at a review gate when a blocking human action is pending.

    This node is intentionally side-effect-light: it does not call LLMs, search,
    parsers, or stage executors. LangGraph resumes an interrupted node from the
    top, so all expensive/non-idempotent work must happen before this gate in
    the normal deterministic stage node.
    """
    sync_interrupt_records(ctx)
    record = get_pending_blocking_interrupt(ctx)
    if record is None:
        return ctx

    payload = build_interrupt_payload(ctx, record)
    record.interrupt_payload = payload

    interrupt = _load_langgraph_interrupt()
    if interrupt is None:
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_runtime_unavailable",
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            after=record,
            metadata={
                "action_id": record.action_id,
                "reason": "langgraph.types.interrupt could not be imported",
            },
        )
        return ctx

    # On the first graph invocation this call raises a LangGraph interrupt and
    # persists the checkpoint. On resume it returns the Command(resume=...) value.
    resume_value: dict[str, Any] | Any = interrupt(payload)

    before = record.model_dump(mode="json")
    record.status = "resumed"
    if isinstance(resume_value, dict):
        record.resume_value = resume_value
    else:
        record.resume_value = {"resume_value": resume_value}
    record.resolved_at = record.resolved_at or datetime.utcnow()
    append_audit_event(
        ctx,
        actor="system",
        event_type="interrupt_resumed_by_langgraph",
        target_type="interrupt_record",
        target_id=record.interrupt_id,
        before=before,
        after=record,
        metadata={"action_id": record.action_id},
    )
    mark_interrupt_resume_consumed(ctx, record.interrupt_id)
    return ctx
