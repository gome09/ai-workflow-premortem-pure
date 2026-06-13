"""Contract tests for EvalExperiment stage resolution operations.

These tests are added for later unified validation. They are not executed as
part of the source patch generation.
"""

from core.models import EvalDataset, EvalExperiment, ProjectContext, SessionState, Stage3Output
from core.stage_resolution_service import build_stage_resolution_operations


def test_incomplete_experiment_binds_run_operation_path() -> None:
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
        status="created",
        eval_ids=["E1"],
        baseline_experiment_id=baseline.experiment_id,
    )
    dataset = EvalDataset(
        session_id=ctx.session_id,
        dataset_id="D1",
        name="regression",
        stage=3,
        tags=["regression"],
        case_ids=["E1"],
        baseline_experiment_id=baseline.experiment_id,
        metadata={"gate_required": True},
    )
    ctx.eval_datasets.append(dataset)
    ctx.eval_experiments.extend([baseline, current])

    operations = build_stage_resolution_operations(ctx, 3)

    op = next(item for item in operations if item.required_resolution == "run_eval_experiment")
    assert op.can_execute_via_api is True
    assert op.api_path == f"/sessions/{ctx.session_id}/eval-experiments/{current.experiment_id}/run"
