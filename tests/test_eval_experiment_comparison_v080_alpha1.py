"""Contract placeholders for v0.8-alpha.1 baseline comparison."""

from core.eval_comparison_service import compare_experiments
from core.models import EvalExperiment, ProjectContext


def test_compare_experiments_returns_non_gate_summary():
    ctx = ProjectContext()
    baseline = EvalExperiment(session_id=ctx.session_id, dataset_id="D", name="baseline")
    current = EvalExperiment(session_id=ctx.session_id, dataset_id="D", name="current")
    ctx.eval_experiments.extend([baseline, current])
    comparison = compare_experiments(
        ctx,
        current_experiment_id=current.experiment_id,
        baseline_experiment_id=baseline.experiment_id,
    )
    assert (
        comparison["gate_effect"]
        == "blocks_stage_advancement_in_v0.8_alpha2_when_regression_detected"
    )
    assert comparison["gate_rule_id"] == "eval_regression"
