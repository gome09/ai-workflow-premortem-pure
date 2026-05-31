# core/eval_metrics_service.py
from __future__ import annotations

from core.models import EvalAggregateMetrics, EvalExperiment, EvalRun, ProjectContext


def _experiment_by_id(ctx: ProjectContext, experiment_id: str) -> EvalExperiment:
    for experiment in ctx.eval_experiments:
        if experiment.experiment_id == experiment_id:
            return experiment
    raise ValueError(f"Eval experiment not found: {experiment_id}")


def _failure_severity_map(ctx: ProjectContext) -> dict[str, str]:
    if not ctx.stage_1_output:
        return {}
    return {item.id: str(item.severity).lower() for item in ctx.stage_1_output.failure_modes}


def _case_scenario_map(ctx: ProjectContext) -> dict[str, str]:
    return {case.eval_id: case.scenario_type for case in ctx.eval_cases}


def compute_experiment_metrics(ctx: ProjectContext, *, experiment_id: str) -> EvalAggregateMetrics:
    experiment = _experiment_by_id(ctx, experiment_id)
    run_id_set = set(experiment.run_ids)
    runs: list[EvalRun] = [run for run in ctx.eval_runs if run.run_id in run_id_set]

    total_cases = len(experiment.eval_ids)
    run_count = len(runs)
    pass_count = len([run for run in runs if run.judge_result == "passed"])
    fail_count = len([run for run in runs if run.judge_result == "failed"])
    needs_review_count = len([run for run in runs if run.judge_result == "needs_review"])
    error_count = len([run for run in runs if run.status == "failed"])

    severity_by_fm = _failure_severity_map(ctx)
    scenario_by_case = _case_scenario_map(ctx)
    scenario_counts: dict[str, int] = {}
    target_node_counts: dict[str, int] = {}
    failed_case_ids: list[str] = []
    needs_review_case_ids: list[str] = []
    high_risk_fail_count = 0
    critical_fail_count = 0
    parser_failure_count = 0
    automated_judgment_count = 0
    human_final_label_count = 0
    estimated_cost_values: list[float] = []
    latency_values: list[int] = []

    for run in runs:
        scenario = scenario_by_case.get(run.eval_id, "unknown")
        scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1
        node_key = run.target_node_id or "unknown"
        target_node_counts[node_key] = target_node_counts.get(node_key, 0) + 1

        if run.estimated_cost is not None:
            estimated_cost_values.append(run.estimated_cost)
        if run.latency_ms is not None:
            latency_values.append(run.latency_ms)

        if "parser" in (run.error_message or "").lower():
            parser_failure_count += 1

        if run.judge_mode in {"rule", "llm", "inherited"}:
            automated_judgment_count += 1
        if run.judge_mode == "human":
            human_final_label_count += 1

        if run.judge_result == "failed":
            failed_case_ids.append(run.eval_id)
            severities = {
                severity_by_fm.get(failure_mode_id, "")
                for failure_mode_id in run.covered_failure_mode_ids
            }
            if "critical" in severities:
                critical_fail_count += 1
            elif "high" in severities:
                high_risk_fail_count += 1
        elif run.judge_result == "needs_review":
            needs_review_case_ids.append(run.eval_id)

    calibrated = [
        calibration
        for calibration in getattr(ctx, "human_calibrations", []) or []
        if calibration.eval_run_id in run_id_set
    ]
    comparable_calibrations = [
        calibration for calibration in calibrated if calibration.agreement is not None
    ]
    human_disagreement_count = len(
        [calibration for calibration in comparable_calibrations if calibration.agreement is False]
    )
    human_disagreement_rate = (
        human_disagreement_count / len(comparable_calibrations) if comparable_calibrations else None
    )

    denominator = run_count or 1
    metrics = EvalAggregateMetrics(
        total_cases=total_cases,
        run_count=run_count,
        pass_count=pass_count,
        fail_count=fail_count,
        needs_review_count=needs_review_count,
        error_count=error_count,
        pass_rate=pass_count / denominator if run_count else 0.0,
        fail_rate=fail_count / denominator if run_count else 0.0,
        needs_review_rate=needs_review_count / denominator if run_count else 0.0,
        critical_fail_count=critical_fail_count,
        high_risk_fail_count=high_risk_fail_count,
        parser_failure_count=parser_failure_count,
        estimated_total_cost=sum(estimated_cost_values) if estimated_cost_values else None,
        average_latency_ms=(sum(latency_values) / len(latency_values)) if latency_values else None,
        scenario_counts=scenario_counts,
        target_node_counts=target_node_counts,
        failed_case_ids=list(dict.fromkeys(failed_case_ids)),
        needs_review_case_ids=list(dict.fromkeys(needs_review_case_ids)),
        automated_judgment_count=automated_judgment_count,
        human_calibration_count=len(calibrated),
        human_disagreement_count=human_disagreement_count,
        human_disagreement_rate=human_disagreement_rate,
        human_final_label_count=human_final_label_count,
    )
    experiment.aggregate_metrics = metrics
    return metrics
