"""Contract placeholders for v0.8-alpha.1 EvalExperiment."""

from core.eval_dataset_service import create_dataset
from core.eval_experiment_service import create_experiment
from core.models import EvalCase, ProjectContext


def test_create_experiment_links_dataset_cases():
    ctx = ProjectContext()
    case = EvalCase(session_id=ctx.session_id, input_payload="input", expected_behavior="expected")
    ctx.eval_cases.append(case)
    dataset = create_dataset(ctx, name="dataset", case_ids=[case.eval_id])
    experiment = create_experiment(ctx, dataset_id=dataset.dataset_id, name="experiment")
    assert experiment.dataset_id == dataset.dataset_id
    assert experiment.eval_ids == [case.eval_id]
    assert experiment.status == "created"
