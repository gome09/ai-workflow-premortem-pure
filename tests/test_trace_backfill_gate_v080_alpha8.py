from core.gates.rules import registered_rules
from core.models import LLMTrace, ProjectContext, SessionState, Stage3Output
from core.stage_readiness_service import evaluate_stage_gate


def test_trace_backfill_gap_rule_is_registered() -> None:
    assert "trace_backfill_gap" in {rule.rule_id for rule in registered_rules()}


def test_trace_backfill_gate_blocks_failed_trace_without_eval_case() -> None:
    ctx = ProjectContext(
        current_state=SessionState.S3_REVIEW,
        research_target="金融交易风控系统",
        domain="金融 / 交易 / 风险控制",
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

    gate = evaluate_stage_gate(ctx, 3)
    blockers = [item for item in gate.blockers if item.blocker_type == "trace_backfill_gap"]

    assert blockers
    assert blockers[0].source_type == "trace"
    assert blockers[0].required_resolution == "trace_to_eval_case"


def test_trace_backfill_gate_blocks_backfilled_case_without_dataset() -> None:
    from core.trace_backfill_service import convert_trace_to_eval_case

    ctx = ProjectContext(
        current_state=SessionState.S3_REVIEW,
        research_target="金融交易风控系统",
        domain="金融 / 交易 / 风险控制",
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
    eval_case = convert_trace_to_eval_case(ctx, trace_id=trace.trace_id)

    gate = evaluate_stage_gate(ctx, 3)
    blockers = [item for item in gate.blockers if item.blocker_type == "trace_backfill_gap"]

    assert any(item.source_id == eval_case.eval_id for item in blockers)
    assert any(item.required_resolution == "create_trace_backfill_dataset" for item in blockers)
