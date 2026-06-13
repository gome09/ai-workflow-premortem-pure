# core/eval_judge.py
from __future__ import annotations

from core.models import EvalCase, EvalRun


def judge_eval_run(case: EvalCase, run: EvalRun) -> EvalRun:
    """Apply the conservative judge to an EvalRun.

    This judge is intentionally transparent and non-autonomous. It never claims
    semantic correctness from a black-box model output unless a later human or
    dedicated LLM judge overrides it. It does, however, separate run-level
    execution signals from the reusable EvalCase definition.
    """
    run.violated_criteria = []

    if run.run_mode == "manual":
        run.judge_mode = "human"
        run.judge_result = "needs_review"
        run.judge_reason = "Manual eval run requires human scoring."
        return run

    if run.run_mode == "dry_run":
        run.judge_mode = "rule"
        run.judge_result = "needs_review"
        run.judge_reason = "Dry run validates eval plumbing but does not execute a target node."
        return run

    run.judge_mode = "rule"
    if not (run.actual_output or "").strip():
        run.judge_result = "failed"
        run.judge_reason = "Target node produced empty output."
        run.violated_criteria.append("actual_output_required")
        return run

    if not (case.expected_behavior or run.expected_behavior or "").strip():
        run.judge_result = "needs_review"
        run.judge_reason = "Expected behavior is empty; human review is required."
        run.violated_criteria.append("expected_behavior_missing")
        return run

    if not (case.pass_criteria or run.pass_criteria):
        run.judge_result = "needs_review"
        run.judge_reason = "Pass criteria are missing; human review is required."
        run.violated_criteria.append("pass_criteria_missing")
        return run

    if case.passed is False:
        run.judge_mode = "inherited"
        run.judge_result = "failed"
        run.judge_reason = (
            "Inherited failed signal from Stage 3 EvalCase; run output should be reviewed."
        )
        run.violated_criteria.append("stage3_predicted_failure")
        return run

    if case.passed is True:
        run.judge_mode = "inherited"
        run.judge_result = "needs_review"
        run.judge_reason = (
            "Stage 3 predicted pass, but run output still requires human confirmation."
        )
        return run

    run.judge_result = "needs_review"
    run.judge_reason = "No automatic semantic judge configured; human review required."
    return run
