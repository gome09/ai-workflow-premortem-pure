"""Contract tests for report-level Eval Regression summary.

These tests are added for later unified validation. They are not executed as
part of the source patch generation.
"""

from core.models import EvalDataset, ProjectContext
from core.report_service import build_report_dict


def test_report_contains_eval_regression_summary() -> None:
    ctx = ProjectContext()
    ctx.eval_datasets.append(
        EvalDataset(
            session_id=ctx.session_id,
            name="regression",
            stage=3,
            tags=["regression"],
            case_ids=["E1"],
        )
    )

    report = build_report_dict(ctx)

    assert "eval_regression_summary" in report
    assert report["eval_regression_summary"]["policy_version"] == "1.2.0"
