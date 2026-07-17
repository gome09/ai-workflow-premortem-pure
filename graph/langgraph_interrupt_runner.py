# graph/langgraph_interrupt_runner.py
from __future__ import annotations

import logging
from typing import Any

from core.audit_service import append_audit_event
from core.config import settings
from core.models import ProjectContext
from graph.interrupt_gate import review_interrupt_gate
from graph.interrupts import (
    get_pending_blocking_interrupt,
    mark_interrupt_resume_consumed,
    sync_interrupt_records,
)
from graph.runner import run_one_step

logger = logging.getLogger(__name__)

_GRAPH_CACHE: Any | None = None
_CHECKPOINTER_RESOURCE: Any | None = None


def _coerce_context(result: Any, fallback: ProjectContext) -> ProjectContext:
    """Normalize LangGraph invoke output back into ProjectContext."""
    if isinstance(result, ProjectContext):
        return result
    if isinstance(result, dict):
        # LangGraph returns __interrupt__ payloads when execution is paused.
        # In that case, keep the already-mutated context as the product state.
        if "__interrupt__" in result:
            return fallback
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
            "thread_id": thread_id or ctx.session_id,
            "checkpoint_ns": "ai_workflow_v0_6_review_gate",
        }
    }


def _load_command_type():
    try:
        from langgraph.types import Command
    except Exception:
        return None
    return Command


def _build_checkpointer() -> Any:
    """Prefer PostgreSQL checkpoints; fall back to memory for local/dev use."""
    global _CHECKPOINTER_RESOURCE
    try:
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver

        conn = psycopg.connect(settings.postgres_dsn_sync)
        # psycopg default Connection row type is tuple; PostgresSaver expects a
        # dict-row Connection. The saver works with the live connection at runtime.
        saver: Any = PostgresSaver(conn)  # type: ignore[arg-type]
        saver.setup()
        _CHECKPOINTER_RESOURCE = conn
        return saver
    except Exception:
        logger.exception(
            "PostgreSQL LangGraph checkpointer unavailable; falling back to in-memory checkpointer."
        )
        try:
            from langgraph.checkpoint.memory import MemorySaver

            saver = MemorySaver()
            _CHECKPOINTER_RESOURCE = saver
            return saver
        except Exception:
            logger.exception(
                "No LangGraph checkpointer available; graph will compile without checkpointing."
            )
            return None


def _build_one_turn_graph():
    """Build a one-turn graph that preserves the deterministic stage model.

    The graph intentionally executes at most one deterministic node per user turn
    and then optionally enters the review interrupt gate. It does not reuse the
    older full-flow builder because that builder starts from node_init and can run
    across multiple stages in one graph invocation.
    """
    from langgraph.graph import END, StateGraph

    graph = StateGraph(ProjectContext)

    def dispatch_one_step(ctx: ProjectContext) -> ProjectContext:
        # If a blocking action already exists, never run a stage node again.
        if get_pending_blocking_interrupt(ctx):
            return ctx
        updated = run_one_step(ctx)
        sync_interrupt_records(updated)
        return updated

    def route_after_dispatch(ctx: ProjectContext) -> str:
        return "review_interrupt_gate" if get_pending_blocking_interrupt(ctx) else "end"

    graph.add_node("dispatch_one_step", dispatch_one_step)
    graph.add_node("review_interrupt_gate", review_interrupt_gate)
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

    checkpointer = _build_checkpointer()
    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)


def get_one_turn_interrupt_graph():
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        _GRAPH_CACHE = _build_one_turn_graph()
    return _GRAPH_CACHE


def invoke_one_turn_with_interrupts(ctx: ProjectContext) -> ProjectContext:
    """Execute one user turn through the experimental LangGraph interrupt path."""
    graph = get_one_turn_interrupt_graph()
    sync_interrupt_records(ctx)
    try:
        result = graph.invoke(ctx, config=_langgraph_config(ctx))
    except Exception:
        logger.exception(
            "LangGraph interrupt runner failed; returning context without fallback stage execution."
        )
        append_audit_event(
            ctx,
            actor="system",
            event_type="interrupt_runner_error",
            target_type="session",
            target_id=ctx.session_id,
            after=ctx,
            metadata={"execution_mode": "langgraph_interrupt"},
        )
        return ctx
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
    if record is None:
        return ctx
    if record.status != "resumed" or record.resume_consumed_at is not None:
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
        result = graph.invoke(
            Command(resume=record.resume_value or {"action_id": action_id}),
            config=_langgraph_config(ctx, thread_id=record.thread_id or ctx.session_id),
        )
        updated = _coerce_context(result, fallback=ctx)
        mark_interrupt_resume_consumed(updated, record.interrupt_id)
        sync_interrupt_records(updated)
        return updated
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
