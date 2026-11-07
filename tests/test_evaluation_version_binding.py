# tests/test_evaluation_version_binding.py
"""Evaluation version digest: stability, invalidation, and binding."""

from __future__ import annotations

from core.approval_service import build_release_readiness
from core.eval_judgment_service import calibrate_eval_run
from core.evaluation_version import (
    build_evaluation_version,
    current_evaluation_digest,
    eval_case_digest,
)
from core.models import (
    EvalCase,
    EvalRun,
    FailureMode,
    LLMTrace,
    Message,
    ProjectContext,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
    StressTestResult,
    TargetDeployment,
    TriggerMethod,
    WorkflowNode,
)
from core.risk.models import RiskFactorScores

_LOW_RISK = RiskFactorScores(
    impact=0, autonomy=0, data_sensitivity=1, reversibility=0, scale=0, external_exposure=0
)


def _ctx() -> ProjectContext:
    ctx = ProjectContext(
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.COMPLETE
    ctx.risk_profile = _LOW_RISK
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="hallucination",
                description="Invents policy clauses",
                severity="high",
            )
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-1",
                stage_name="Answer generation",
                model_assigned="model",
                human_action="review",
                check_criteria="citations",
                failure_modes_addressed=["FM-001"],
                prompt_template="answer",
            )
        ]
    )
    ctx.stage_3_output = Stage3Output(
        test_results=[
            StressTestResult(
                tested_node_id="N-1",
                scenario_type="normal",
                test_input="policy question",
                ai_output="answer",
                pass_criteria=["citation"],
                passed=True,
            )
        ]
    )
    ctx.stage_4_output = Stage4Output(
        trigger_methods=[
            TriggerMethod(
                node_id="N-1",
                model_or_mode="model",
                entry_point="chat",
                trigger_instruction="ask",
                execution_suggestion="run",
            )
        ]
    )
    ctx.stage_output_versions = {
        "stage_1": 1,
        "stage_2": 1,
        "stage_3": 1,
        "stage_4": 1,
    }
    ctx.target_deployment = TargetDeployment(
        endpoint="http://target.local/eval", version="2026.11.1"
    )
    ctx.eval_cases.append(
        EvalCase(
            session_id=ctx.session_id,
            stage_id=3,
            target_node_id="N-1",
            scenario_type="normal",
            input_payload="policy question",
            expected_behavior="answer",
            pass_criteria=["citation"],
        )
    )
    return ctx


def test_digest_is_stable_and_reproducible():
    ctx = _ctx()
    first = build_evaluation_version(ctx)
    second = build_evaluation_version(ctx)

    assert first == second
    assert first["schema"] == "2.0"
    assert first["stage_versions"] == ctx.stage_output_versions
    assert first["input_versions"] == {}
    assert first["content_digest"]
    assert first["digest"]


def test_conversation_and_traces_do_not_change_digest():
    ctx = _ctx()
    before = current_evaluation_digest(ctx)

    ctx.conversation_history["stage_1"] = [Message(role="user", content="chat noise")]
    ctx.llm_traces.append(
        LLMTrace(session_id=ctx.session_id, stage=1, node_name="noise", model="model")
    )

    assert current_evaluation_digest(ctx) == before


def test_stage1_content_change_changes_digest():
    ctx = _ctx()
    before = current_evaluation_digest(ctx)

    ctx.stage_1_output.failure_modes[0].category = "changed category"

    assert current_evaluation_digest(ctx) != before


def test_stage_version_bump_prevents_resurrection():
    ctx = _ctx()
    original_digest = current_evaluation_digest(ctx)

    ctx.stage_1_output.failure_modes[0].category = "changed category"
    changed_digest = current_evaluation_digest(ctx)
    assert changed_digest != original_digest

    # Revert content but keep the bumped version: an approval must not revive.
    ctx.stage_1_output.failure_modes[0].category = "hallucination"
    ctx.stage_output_versions["stage_1"] = 2
    reverted_digest = current_evaluation_digest(ctx)

    assert reverted_digest != original_digest


def test_old_digest_eval_run_is_not_current_release_evidence():
    ctx = _ctx()
    ctx.eval_runs.append(
        EvalRun(
            session_id=ctx.session_id,
            eval_id="EVAL-OLD",
            target_node_id="N-1",
            run_mode="target_http",
            execution_kind="real_target_execution",
            execution_outcome="success",
            evaluation_version_digest="old-digest",
            input_payload="policy question",
            expected_behavior="answer",
            pass_criteria=["citation"],
            actual_output="answer",
            judge_result="passed",
            status="completed",
        )
    )

    readiness = build_release_readiness(ctx)

    assert readiness.passed_real_test_node_ids == []
    assert any(
        blocker.code in {"release_batch", "real_target_test"} for blocker in readiness.blockers
    )


def test_current_digest_eval_run_is_counted():
    ctx = _ctx()
    current_digest = current_evaluation_digest(ctx)
    case = ctx.eval_cases[0]
    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        target_node_id="N-1",
        run_mode="target_http",
        execution_kind="real_target_execution",
        execution_outcome="success",
        evaluation_version_digest=current_digest,
        target_endpoint=ctx.target_deployment.endpoint,
        target_deployment_version=ctx.target_deployment.version,
        case_version_digest=eval_case_digest(case),
        input_payload="policy question",
        expected_behavior="answer",
        pass_criteria=["citation"],
        actual_output="answer",
        judge_result="passed",
        status="completed",
    )
    ctx.eval_runs.append(run)
    calibrate_eval_run(
        ctx,
        eval_run_id=run.run_id,
        human_label="passed",
        human_comment="人工核对输出满足 pass_criteria。",
        reviewer_id="reviewer-b",
        actor_role="editor",
    )

    readiness = build_release_readiness(ctx)

    assert "N-1" in readiness.passed_real_test_node_ids
