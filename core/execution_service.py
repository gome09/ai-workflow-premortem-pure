# core/execution_service.py
from __future__ import annotations

import logging
from typing import Any

from core.config import settings
from core.execution_mode import WorkflowExecutionMode
from core.models import ProjectContext
from core.version import APP_VERSION
from graph.langgraph_interrupt_runner import invoke_one_turn_with_interrupts
from graph.runner import run_one_step

logger = logging.getLogger(__name__)


def reconcile_pending_interrupt_resumes(limit: int = 100) -> dict[str, int]:
    """Retry durable interrupt resumes left incomplete by a crash or outage."""
    from storage import cache as cache_module
    from storage import session_store as session_store_module

    session_store = session_store_module.session_store
    context_cache = cache_module.context_cache
    mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
    summary = {"found": 0, "claimed": 0, "completed": 0, "failed": 0}
    if mode != WorkflowExecutionMode.LANGGRAPH_INTERRUPT:
        return summary
    if not all(
        callable(getattr(session_store, name, None))
        for name in (
            "list_pending_interrupt_resumes",
            "claim_interrupt_resume",
            "complete_interrupt_resume",
        )
    ):
        return summary

    items = session_store.list_pending_interrupt_resumes(limit=limit)
    summary["found"] = len(items)
    for item in items:
        interrupt_id = item["interrupt_id"]
        if not session_store.claim_interrupt_resume(interrupt_id):
            continue
        summary["claimed"] += 1
        try:
            ctx = session_store.load(item["session_id"], item.get("tenant_id") or "")
            if ctx is None:
                raise ValueError(f"Session not found: {item['session_id']}")
            from graph.langgraph_interrupt_runner import consume_resumable_interrupt_if_needed

            updated = consume_resumable_interrupt_if_needed(ctx, item["action_id"])
            record = next(
                (
                    record
                    for record in updated.interrupt_records
                    if record.interrupt_id == interrupt_id
                ),
                None,
            )
            if record is None or record.resume_consumed_at is None:
                raise RuntimeError("LangGraph interrupt resume was not consumed")
            session_store.save(updated)
            context_cache.set(updated)
            session_store.complete_interrupt_resume(interrupt_id)
            summary["completed"] += 1
        except Exception as exc:  # noqa: BLE001 - durable failure is recorded for retry
            session_store.complete_interrupt_resume(interrupt_id, error=str(exc))
            summary["failed"] += 1
            logger.exception("Interrupt resume reconciliation failed: %s", interrupt_id)
    return summary


def prepare_execution_after_action_resolutions(
    ctx: ProjectContext, action_ids: list[str]
) -> ProjectContext:
    """Materialize policy-approved resume records before the atomic store save."""
    if (
        WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
        != WorkflowExecutionMode.LANGGRAPH_INTERRUPT
    ):
        return ctx
    from graph.interrupts import (
        mark_interrupt_cancelled_from_action,
        mark_interrupt_resumed_from_action,
    )
    from graph.transition_policy import evaluate_action_resolution

    for action_id in action_ids:
        action = next((item for item in ctx.pending_actions if item.action_id == action_id), None)
        if action is None or not action.reviewer_decision:
            continue
        effect = evaluate_action_resolution(
            action,
            action.reviewer_decision,
            payload_after=action.payload_after,
        )
        if effect.allow_continue:
            mark_interrupt_resumed_from_action(ctx, action_id, policy_effect=effect)
        else:
            mark_interrupt_cancelled_from_action(
                ctx,
                action_id,
                reason=effect.message,
                policy_effect=effect,
            )
    return ctx


def execute_one_turn(ctx: ProjectContext) -> ProjectContext:
    """Run exactly one user turn through the configured execution mode."""
    ctx.llm_call_count = getattr(ctx, "llm_call_count", 0) + 1
    # T3.5 记录前一次 token 估算，用于推算本轮 token_delta
    prev_token_estimate = getattr(ctx, "llm_token_estimate", 0) or 0
    mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
    if mode == WorkflowExecutionMode.SINGLE_STEP:
        result = run_one_step(ctx)
    elif mode == WorkflowExecutionMode.LANGGRAPH_INTERRUPT:
        result = invoke_one_turn_with_interrupts(ctx)
    else:
        raise ValueError(f"Unsupported workflow execution mode in {APP_VERSION}: {mode}")

    # T2.1 LLM10: 从既有 traces 聚合 token 估算（forward-only，不回溯历史）
    result.llm_token_estimate = _sum_trace_tokens(result)
    _check_unbounded_consumption(result)
    # T3.5 LLM 用量指标打点（失败不阻断主路径）
    try:
        from api.metrics import record_llm_usage

        token_delta = max(0, (result.llm_token_estimate or 0) - prev_token_estimate)
        record_llm_usage(call_count_delta=1, token_delta=token_delta)
    except Exception:
        logger.debug("record_llm_usage failed; non-fatal", exc_info=True)
    return result


def _sum_trace_tokens(ctx: ProjectContext) -> int:
    """Aggregate input+output token counts from llm_traces."""
    total = 0
    for trace in getattr(ctx, "llm_traces", []) or []:
        if trace.input_token_count:
            total += int(trace.input_token_count)
        if trace.output_token_count:
            total += int(trace.output_token_count)
    return total


def _check_unbounded_consumption(ctx: ProjectContext) -> None:
    """T2.1 LLM10: 超阈值产出 unbounded_consumption finding（告警不阻断）。"""
    from tools.safety_classifier import scan_unbounded_consumption

    try:
        scan_unbounded_consumption(ctx)
    except Exception:
        logger.exception("unbounded_consumption check failed; non-fatal")


def sync_execution_after_action_resolution(
    ctx: ProjectContext,
    action_id: str,
    *,
    policy_effect: Any | None = None,
    reason: str = "",
) -> ProjectContext:
    """Synchronize execution-layer state after a business action is resolved.

    Business review decisions originate from PendingHumanAction in
    core.oversight_service. The execution layer is the only place that may map
    those decisions to LangGraph interrupt/checkpoint behavior.

    - single_step remains a deterministic, non-checkpoint execution path.
    - langgraph_interrupt may mark the mapped interrupt as resumed/cancelled and
      consume Command(resume=...) exactly once.

    This keeps Evidence, Safety, Eval, Report, and Oversight services from
    mutating workflow execution semantics directly.
    """
    mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
    if mode == WorkflowExecutionMode.SINGLE_STEP:
        return ctx

    if mode != WorkflowExecutionMode.LANGGRAPH_INTERRUPT:
        raise ValueError(f"Unsupported workflow execution mode in {APP_VERSION}: {mode}")

    try:
        from graph.interrupts import (
            mark_interrupt_cancelled_from_action,
            mark_interrupt_resumed_from_action,
        )
        from graph.langgraph_interrupt_runner import consume_resumable_interrupt_if_needed

        if policy_effect is None:
            action = next(
                (item for item in ctx.pending_actions if item.action_id == action_id), None
            )
            if action is not None and action.reviewer_decision:
                try:
                    from graph.transition_policy import evaluate_action_resolution

                    policy_effect = evaluate_action_resolution(
                        action,
                        action.reviewer_decision,
                        payload_after=action.payload_after,
                    )
                except Exception:
                    logger.exception(
                        "Could not reconstruct policy effect for action_id=%s", action_id
                    )

        allow_continue = bool(getattr(policy_effect, "allow_continue", False))
        if allow_continue:
            from storage import session_store as session_store_module

            session_store = session_store_module.session_store
            record = mark_interrupt_resumed_from_action(ctx, action_id, policy_effect=policy_effect)
            if record is None:
                return ctx
            session_store.enqueue_interrupt_resume(ctx, record)
            if not session_store.claim_interrupt_resume(record.interrupt_id):
                return ctx
            updated = consume_resumable_interrupt_if_needed(ctx, action_id)
            consumed = next(
                (
                    item.resume_consumed_at is not None
                    for item in updated.interrupt_records
                    if item.interrupt_id == record.interrupt_id
                ),
                False,
            )
            session_store.complete_interrupt_resume(
                record.interrupt_id,
                error="" if consumed else "LangGraph interrupt resume was not consumed",
            )
            return updated

        mark_interrupt_cancelled_from_action(
            ctx,
            action_id,
            reason=reason
            or getattr(policy_effect, "message", "Action resolution does not allow continuation."),
            policy_effect=policy_effect,
        )
        return ctx
    except Exception:
        logger.exception(
            "Failed to synchronize execution state after action resolution: action_id=%s",
            action_id,
        )
        return ctx


def sync_execution_after_action_resolutions(
    ctx: ProjectContext,
    action_ids: list[str],
    *,
    reason: str = "",
) -> ProjectContext:
    """Synchronize multiple indirectly resolved actions.

    Used by evidence verification, safety finding resolution, and other helper
    APIs that can close several PendingHumanAction records without the user
    calling /actions/{action_id}/resolve directly.
    """
    for action_id in action_ids:
        ctx = sync_execution_after_action_resolution(
            ctx,
            action_id,
            reason=reason,
        )
    return ctx


def sync_execution_after_stage_revision(
    ctx: ProjectContext,
    stage: int,
    *,
    reason: str = "",
    superseded_action_ids: list[str] | None = None,
) -> ProjectContext:
    """Synchronize execution-layer records after a stage is revised/backed.

    This does not advance the workflow and does not run LangGraph. It only gives
    the guarded interrupt adapter one coordination point for action records
    that were superseded by a new stage_output_version.
    """
    mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
    if mode == WorkflowExecutionMode.SINGLE_STEP:
        return ctx
    if mode != WorkflowExecutionMode.LANGGRAPH_INTERRUPT:
        raise ValueError(f"Unsupported workflow execution mode in {APP_VERSION}: {mode}")

    try:
        from graph.interrupts import sync_interrupt_records

        sync_interrupt_records(ctx)
        return ctx
    except Exception:
        logger.exception(
            "Failed to synchronize execution state after stage revision: stage=%s action_ids=%s",
            stage,
            superseded_action_ids or [],
        )
        return ctx
