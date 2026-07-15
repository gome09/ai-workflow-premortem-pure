from __future__ import annotations

from typing import Any

from core.models import LLMTrace, ProjectContext


def create_llm_trace(
    ctx: ProjectContext,
    *,
    stage: int | None,
    node_name: str,
    trace_type: str = "llm",
    provider: str = "openai_compatible",
    model: str = "",
    prompt_template_id: str = "",
    latency_ms: int | None = None,
    parser_status: str = "pending",
    retry_count: int = 0,
    error_type: str | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> LLMTrace:
    return LLMTrace(
        session_id=ctx.session_id,
        stage=stage,
        node_name=node_name,
        trace_type=trace_type,  # type: ignore[arg-type]
        provider=provider,
        model=model,
        prompt_template_id=prompt_template_id,
        latency_ms=latency_ms,
        parser_status=parser_status,
        retry_count=retry_count,
        error_type=error_type,
        error_message=error_message,
        evidence_count=len(getattr(ctx, "evidence_sources", []) or []),
        metadata=metadata or {},
    )


def append_llm_trace(ctx: ProjectContext, trace: LLMTrace) -> LLMTrace:
    ctx.llm_traces.append(trace)
    return trace
