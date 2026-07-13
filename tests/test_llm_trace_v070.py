"""v0.7 trace metadata tests for later unified validation."""

from __future__ import annotations

from core.models import ProjectContext
from core.traces import append_llm_trace, create_llm_trace


def test_trace_supports_type_and_metadata():
    ctx = ProjectContext()
    trace = append_llm_trace(
        ctx,
        create_llm_trace(
            ctx,
            stage=1,
            node_name="stage_1_parser",
            trace_type="parser",
            parser_status="validation_failed",
            metadata={"validation_errors": ["fixture"]},
        ),
    )

    assert trace.trace_type == "parser"
    assert trace.metadata["validation_errors"] == ["fixture"]
    assert ctx.llm_traces[0].trace_id == trace.trace_id
