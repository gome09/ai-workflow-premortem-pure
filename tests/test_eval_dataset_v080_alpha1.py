"""Contract placeholders for v0.8-alpha.1 EvalDataset.

These tests are intended for the later unified validation pass and are not run
during this source-level patch.
"""

from core.eval_dataset_service import create_dataset_from_stage3
from core.models import EvalCase, ProjectContext


def test_create_dataset_from_stage3_collects_eval_cases():
    ctx = ProjectContext()
    ctx.eval_cases.append(
        EvalCase(
            session_id=ctx.session_id,
            input_payload="input",
            expected_behavior="expected",
        )
    )
    dataset = create_dataset_from_stage3(ctx, name="stage3")
    assert dataset.case_ids == [ctx.eval_cases[0].eval_id]
    assert dataset.source == "stage3_generated"
