"""Contract placeholders for v0.8-alpha.1 experiment metrics."""

from core.eval_dataset_service import create_dataset
from core.eval_experiment_service import create_experiment, run_experiment
from core.models import EvalCase, ProjectContext


def test_run_experiment_computes_metrics_dry_run():
    ctx = ProjectContext()
    case = EvalCase(session_id=ctx.session_id, input_payload="input", expected_behavior="expected")
    ctx.eval_cases.append(case)
    dataset = create_dataset(ctx, name="dataset", case_ids=[case.eval_id])
    experiment = create_experiment(
        ctx, dataset_id=dataset.dataset_id, name="experiment", run_mode="dry_run"
    )
    experiment = run_experiment(ctx, experiment_id=experiment.experiment_id, dry_run_only=True)
    assert experiment.status == "completed"
    assert experiment.aggregate_metrics.run_count == 1
