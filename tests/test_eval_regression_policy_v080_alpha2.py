"""Contract tests for v0.8-alpha.2 Eval Regression policy.

These tests are added for later unified validation. They are not executed as
part of the source patch generation.
"""

from core.eval_regression_policy import (
    build_regression_decision,
    dataset_case_hash,
    is_gate_relevant_dataset,
)
from core.models import EvalDataset, EvalExperiment, ProjectContext


def test_dataset_case_hash_is_order_independent() -> None:
    assert dataset_case_hash(["A", "B"]) == dataset_case_hash(["B", "A"])


def test_gate_relevant_dataset_detects_regression_tag() -> None:
    dataset = EvalDataset(
        session_id="S",
        name="stage3 regression",
        stage=3,
        scenario_type="mixed",
        tags=["stage3", "regression"],
        case_ids=["E1"],
    )
    assert is_gate_relevant_dataset(dataset, stage=3) is True


def test_missing_current_experiment_blocks_after_baseline() -> None:
    ctx = ProjectContext()
    baseline = EvalExperiment(
        session_id=ctx.session_id,
        dataset_id="D1",
        name="baseline",
        status="completed",
        eval_ids=["E1"],
    )
    dataset = EvalDataset(
        session_id=ctx.session_id,
        dataset_id="D1",
        name="stage3 regression",
        stage=3,
        tags=["regression"],
        case_ids=["E1"],
        baseline_experiment_id=baseline.experiment_id,
    )
    ctx.eval_datasets.append(dataset)
    ctx.eval_experiments.append(baseline)

    decision = build_regression_decision(ctx, dataset)

    assert decision.blocking is True
    assert decision.status == "missing_current_experiment"
    assert decision.required_resolution == "create_eval_experiment"
