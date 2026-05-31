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


def execute_one_turn(ctx: ProjectContext) -> ProjectContext:
    """Run exactly one user turn through the configured execution mode."""
    mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
    if mode == WorkflowExecutionMode.SINGLE_STEP:
        return run_one_step(ctx)
    if mode == WorkflowExecutionMode.LANGGRAPH_INTERRUPT:
        return invoke_one_turn_with_interrupts(ctx)
    raise ValueError(f"Unsupported workflow execution mode in {APP_VERSION}: {mode}")


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
            mark_interrupt_resumed_from_action(ctx, action_id, policy_effect=policy_effect)
            return consume_resumable_interrupt_if_needed(ctx, action_id)

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
    the experimental interrupt adapter one coordination point for action records
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
