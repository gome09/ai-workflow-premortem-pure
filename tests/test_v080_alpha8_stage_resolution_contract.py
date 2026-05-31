from core.gates.rules.trace_backfill_gap import rule as trace_backfill_rule
from core.models import LLMTrace, ProjectContext, SessionState, Stage3Output
from core.stage_advancement_contract import contract_summary, operation_contract_for
from core.stage_resolution_service import build_stage_resolution_operations


def test_trace_backfill_contract_is_declared() -> None:
    summary = contract_summary()

    assert "trace_backfill_gap" in summary["blocker_types"]
    assert "trace_to_eval_case" in summary["required_resolutions"]
    assert "create_trace_backfill_dataset" in summary["required_resolutions"]
    assert operation_contract_for("trace_to_eval_case")["api_path_template"] == (
        "/sessions/{session_id}/traces/{trace_id}/to-eval-case"
    )


def test_trace_backfill_operation_binds_trace_api_path() -> None:
    """High-risk context triggers trace_backfill_gap → operation binds api_path."""
    ctx = ProjectContext(
        research_target="medication management system",
        domain="healthcare / pharmacy / patient safety",
        goal="manage patient medication records and drug interaction checks",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    trace = LLMTrace(
        session_id=ctx.session_id,
        stage=3,
        node_name="stage3_parser",
        trace_type="parser",
        parser_status="failed",
        error_type="parser_error",
        error_message="invalid json",
    )
    ctx.llm_traces.append(trace)

    operations = build_stage_resolution_operations(ctx, 3)
    trace_operations = [
        item for item in operations if item.required_resolution == "trace_to_eval_case"
    ]

    assert trace_operations
    assert trace_operations[0].api_path == (
        f"/sessions/{ctx.session_id}/traces/{trace.trace_id}/to-eval-case"
    )


def test_low_risk_trace_backfill_returns_no_blockers() -> None:
    """Low-risk context: trace_backfill_gap rule returns empty (not blocking)."""
    ctx = ProjectContext(
        research_target="personal reading and learning plan management",
        domain="personal learning / reading plan / local use",
        goal="help individuals create and track reading plans",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    ctx.llm_traces.append(
        LLMTrace(
            session_id=ctx.session_id,
            stage=3,
            node_name="stage3_parser",
            trace_type="parser",
            parser_status="failed",
            error_type="parser_error",
            error_message="invalid json",
        )
    )

    blockers = trace_backfill_rule.evaluate(ctx, 3)
    assert blockers == []
