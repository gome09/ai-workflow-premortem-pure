# core/eval_comparison_service.py
from __future__ import annotations

from core.eval_metrics_service import compute_experiment_metrics
from core.models import EvalExperiment, ProjectContext

MAX_PASS_RATE_DROP = 0.05


def _experiment_by_id(ctx: ProjectContext, experiment_id: str) -> EvalExperiment:
    for experiment in ctx.eval_experiments:
        if experiment.experiment_id == experiment_id:
            return experiment
    raise ValueError(f"Eval experiment not found: {experiment_id}")


def compare_experiments(
    ctx: ProjectContext,
    *,
    current_experiment_id: str,
    baseline_experiment_id: str,
) -> dict:
    current = _experiment_by_id(ctx, current_experiment_id)
    baseline = _experiment_by_id(ctx, baseline_experiment_id)

    current_metrics = compute_experiment_metrics(ctx, experiment_id=current.experiment_id)
    baseline_metrics = compute_experiment_metrics(ctx, experiment_id=baseline.experiment_id)

    pass_rate_delta = current_metrics.pass_rate - baseline_metrics.pass_rate
    critical_fail_count_delta = (
        current_metrics.critical_fail_count - baseline_metrics.critical_fail_count
    )
    high_risk_fail_count_delta = (
        current_metrics.high_risk_fail_count - baseline_metrics.high_risk_fail_count
    )
    needs_review_count_delta = (
        current_metrics.needs_review_count - baseline_metrics.needs_review_count
    )
    parser_failure_count_delta = (
        current_metrics.parser_failure_count - baseline_metrics.parser_failure_count
    )

    reasons: list[str] = []
    if pass_rate_delta < -MAX_PASS_RATE_DROP:
        reasons.append("pass_rate_drop_exceeds_5_percent")
    if critical_fail_count_delta > 0:
        reasons.append("critical_fail_count_increased")
    if high_risk_fail_count_delta > 0:
        reasons.append("high_risk_fail_count_increased")
    if parser_failure_count_delta > 0:
        reasons.append("parser_failure_count_increased")

    comparison = {
        "baseline_experiment_id": baseline.experiment_id,
        "current_experiment_id": current.experiment_id,
        "baseline_status": baseline.status,
        "current_status": current.status,
        "baseline_pass_rate": baseline_metrics.pass_rate,
        "current_pass_rate": current_metrics.pass_rate,
        "pass_rate_delta": pass_rate_delta,
        "critical_fail_count_delta": critical_fail_count_delta,
        "high_risk_fail_count_delta": high_risk_fail_count_delta,
        "needs_review_count_delta": needs_review_count_delta,
        "parser_failure_count_delta": parser_failure_count_delta,
        "regression_detected": bool(reasons),
        "regression_reasons": reasons,
        "gate_effect": "blocks_stage_advancement_in_v0.8_alpha2_when_regression_detected",
        "gate_rule_id": "eval_regression",
    }
    current.comparison_summary = comparison
    return comparison
