# graph/langgraph_interrupt_runner.py
from __future__ import annotations

import logging
from typing import Any, TypedDict

from core.audit_service import append_audit_event
from core.models import ProjectContext
from graph.checkpoint_manager import (
    checkpoint_manager,
    checkpoint_namespace,
    checkpoint_thread_id,
)
from graph.interrupt_gate import review_interrupt_gate
from graph.interrupts import (
    get_pending_blocking_interrupt,
    mark_interrupt_resume_consumed,
    sync_interrupt_records,
)
from graph.runner import run_one_step

logger = logging.getLogger(__name__)

_GRAPH_CACHE: Any | None = None


class InterruptGraphState(TypedDict):
    """Single encrypted checkpoint channel containing workflow product state."""

    context: ProjectContext


def _coerce_context(result: Any, fallback: ProjectContext) -> ProjectContext:
    """Normalize LangGraph invoke output back into ProjectContext."""
    if isinstance(result, ProjectContext):
        return result
    if isinstance(result, dict):
        context = result.get("context")
        if isinstance(context, ProjectContext):
            return context
        if isinstance(context, dict):
            try:
                return ProjectContext.model_validate(context)
            except Exception:
                logger.exception("Could not validate context channel from LangGraph result.")
        try:
            return ProjectContext.model_validate(result)
        except Exception:
            logger.exception(
                "Could not coerce LangGraph result to ProjectContext; using fallback context."
            )
            return fallback
    return fallback


def _langgraph_config(ctx: ProjectContext, thread_id: str | None = None) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": thread_id or checkpoint_thread_id(ctx),
            "checkpoint_ns": checkpoint_namespace(),
        }
    }


def _load_command_type() -> Any:
    # -> Any：返回 langgraph.types.Command 类本身；为免惰性加载边界引入 TYPE_CHECKING 导入，保持 Any
    try:
        from langgraph.types import Command
    except Exception:
        return None
    return Command


def _build_one_turn_graph() -> Any:
    # -> Any：编译图实为 CompiledStateGraph[ProjectContext, ...]；为免惰性加载边界引入 TYPE_CHECKING 导入，保持 Any
    """Build a one-turn graph that preserves the deterministic stage model.

    The graph intentionally executes at most one deterministic node per user turn
    and then optionally enters the review interrupt gate. It does not reuse the
    older full-flow builder because that builder starts from node_init and can run
    across multiple stages in one graph invocation.
    """
    from langgraph.graph import END, StateGraph

    graph = StateGraph(InterruptGraphState)

    def dispatch_one_step(state: InterruptGraphState) -> InterruptGraphState:
        ctx = state["context"]
        # If a blocking action already exists, never run a stage node again.
        if get_pending_blocking_interrupt(ctx):
            return {"context": ctx}
        updated = run_one_step(ctx)
        sync_interrupt_records(updated)
        return {"context": updated}

    def route_after_dispatch(state: InterruptGraphState) -> str:
        ctx = state["context"]
        return "review_interrupt_gate" if get_pending_blocking_interrupt(ctx) else "end"

    def interrupt_gate(state: InterruptGraphState) -> InterruptGraphState:
        return {"context": review_interrupt_gate(state["context"])}

    # add_node overloads reject a plain ProjectContext->ProjectContext callable in langgraph's
    # generic StateGraph typing; the node contract holds at runtime.
    graph.add_node("dispatch_one_step", dispatch_one_step)
    graph.add_node("review_interrupt_gate", interrupt_gate)
    graph.set_entry_point("dispatch_one_step")
    graph.add_conditional_edges(
        "dispatch_one_step",
        route_after_dispatch,
        {
            "review_interrupt_gate": "review_interrupt_gate",
            "end": END,
        },
    )
    graph.add_edge("review_interrupt_gate", END)

    return graph.compile(checkpointer=checkpoint_manager.get_saver())


def get_one_turn_interrupt_graph() -> Any:
    # -> Any：缓存 _build_one_turn_graph() 的编译图（CompiledStateGraph[ProjectContext, ...]）；为免惰性加载边界引入 TYPE_CHECKING 导入，保持 Any
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        _GRAPH_CACHE = _build_one_turn_graph()
    return _GRAPH_CACHE


def invoke_one_turn_with_interrupts(ctx: ProjectContext) -> ProjectContext:
    """Execute one user turn through the guarded LangGraph interrupt path."""
    graph = get_one_turn_interrupt_graph()
    sync_interrupt_records(ctx)
    try:
        result = graph.invoke({"context": ctx}, config=_langgraph_config(ctx))
    except Exception as exc:
        logger.exception("LangGraph interrupt runner failed; refusing fallback stage execution.")
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_runner_error",
            target_type="session",
            target_id=ctx.session_id,
            after=ctx,
            metadata={"execution_mode": "langgraph_interrupt"},
        )
        raise RuntimeError("LangGraph interrupt execution failed") from exc
    updated = _coerce_context(result, fallback=ctx)
    sync_interrupt_records(updated)
    return updated


def consume_resumable_interrupt_if_needed(ctx: ProjectContext, action_id: str) -> ProjectContext:
    """Consume Command(resume=...) for one resolved action-linked interrupt.

    Only interrupts already marked as resumed by the oversight policy are sent to
    LangGraph. Cancelled/rejected/superseded actions are never resumed.
    """
    sync_interrupt_records(ctx)
    record = next((item for item in ctx.interrupt_records if item.action_id == action_id), None)
    action = next((item for item in ctx.pending_actions if item.action_id == action_id), None)
    if record is None:
        return ctx
    if record.status != "resumed" or record.resume_consumed_at is not None:
        return ctx
    expected_thread_id = checkpoint_thread_id(ctx)
    expected_version = ctx.stage_output_versions.get(f"stage_{record.stage_id}", 1)
    if (
        action is None
        or action.status != "resolved"
        or action.reviewer_decision == "reject"
        or record.thread_id != expected_thread_id
        or record.checkpoint_ns != checkpoint_namespace()
        or record.node_name != (action.node_id or f"stage_{action.stage_id}_review_gate")
        or record.stage_id != action.stage_id
        or record.stage_output_version != action.stage_output_version
        or record.stage_output_version != expected_version
        or not isinstance(record.resume_value, dict)
        or record.resume_value.get("allow_continue") is not True
        or record.resume_value.get("action_id") != action_id
        or record.resume_value.get("decision") != action.reviewer_decision
    ):
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_resume_rejected",
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            after=record,
            metadata={
                "action_id": action_id,
                "reason": "stale or mismatched interrupt checkpoint metadata",
            },
        )
        return ctx

    Command = _load_command_type()
    if Command is None:
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_resume_not_consumed",
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            after=record,
            metadata={
                "action_id": action_id,
                "reason": "langgraph.types.Command could not be imported",
            },
        )
        return ctx

    try:
        graph = get_one_turn_interrupt_graph()
        graph.invoke(
            Command(resume=record.resume_value or {"action_id": action_id}),
            config=_langgraph_config(ctx, thread_id=expected_thread_id),
        )
        # The checkpoint contains the product state as it existed before the
        # human decision. Never merge that stale snapshot back over the latest
        # authoritative context loaded from the session store. The resume is an
        # execution acknowledgement only; business state remains authoritative.
        mark_interrupt_resume_consumed(ctx, record.interrupt_id)
        sync_interrupt_records(ctx)
        return ctx
    except Exception as exc:
        logger.exception("Failed to consume LangGraph resume for action_id=%s", action_id)
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_resume_failed",
            target_type="interrupt_record",
            target_id=record.interrupt_id,
            after=record,
            metadata={"action_id": action_id, "error": str(exc)},
        )
        return ctx
