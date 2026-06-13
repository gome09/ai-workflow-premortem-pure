"""Contract tests for v0.8-alpha.2 Eval Regression Gate.

These tests are added for later unified validation. They are not executed as
part of the source patch generation.
"""

from core.gates.rules import registered_rules
from core.models import EvalDataset, EvalExperiment, ProjectContext, SessionState, Stage3Output
from core.stage_readiness_service import evaluate_stage_gate


def test_eval_regression_rule_is_registered() -> None:
    assert "eval_regression" in {rule.rule_id for rule in registered_rules()}


def test_stage3_regression_comparison_blocks_advancement() -> None:
    ctx = ProjectContext(current_state=SessionState.S3_REVIEW)
    ctx.stage_3_output = Stage3Output()
    baseline = EvalExperiment(
        session_id=ctx.session_id,
        dataset_id="D1",
        name="baseline",
        status="completed",
        eval_ids=["E1"],
    )
    current = EvalExperiment(
        session_id=ctx.session_id,
        dataset_id="D1",
        name="current",
        status="completed",
        eval_ids=["E1"],
        baseline_experiment_id=baseline.experiment_id,
        comparison_summary={
            "baseline_experiment_id": baseline.experiment_id,
            "current_experiment_id": "current",
            "regression_detected": True,
            "regression_reasons": ["pass_rate_drop_exceeds_5_percent"],
            "pass_rate_delta": -0.10,
            "critical_fail_count_delta": 0,
        },
    )
    dataset = EvalDataset(
        session_id=ctx.session_id,
        dataset_id="D1",
        name="regression",
        stage=3,
        tags=["stage3", "regression"],
        case_ids=["E1"],
        baseline_experiment_id=baseline.experiment_id,
        metadata={"gate_required": True},  # v0.8.0-beta.2: risk-adaptive gate
    )
    ctx.eval_datasets.append(dataset)
    ctx.eval_experiments.extend([baseline, current])

    gate = evaluate_stage_gate(ctx, 3)

    blocker = next(item for item in gate.blockers if item.blocker_type == "eval_regression")
    assert gate.can_continue is False
    assert blocker.rule_id == "eval_regression"
    assert blocker.required_resolution == "revise_stage"
    assert blocker.can_be_overridden_by_approval is False
