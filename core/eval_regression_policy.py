# core/eval_regression_policy.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from core.models import EvalDataset, EvalExperiment, ProjectContext
from core.version import APP_VERSION

# v0.8.0-alpha.2 keeps thresholds close to the alpha.1 comparison semantics.
# Later releases can move these to core.config without changing gate callers.
EVAL_REGRESSION_MAX_PASS_RATE_DROP = 0.05
EVAL_REGRESSION_MAX_CRITICAL_FAIL_INCREASE = 0
EVAL_REGRESSION_MAX_HIGH_RISK_FAIL_INCREASE = 0
EVAL_REGRESSION_MAX_PARSER_FAILURE_INCREASE = 0
GATE_RELEVANT_TAGS = {"gate_required", "stage3", "regression"}
GATE_RELEVANT_SCENARIOS = {"regression", "safety", "adversarial", "parser", "production_failure"}

DecisionStatus = Literal[
    "not_gate_relevant",
    "dataset_empty",
    "missing_baseline",
    "missing_current_experiment",
    "experiment_not_completed",
    "experiment_stale_for_dataset",
    "missing_comparison",
    "regression_detected",
    "passed",
]


@dataclass(frozen=True)
class EvalRegressionDecision:
    """Pure-read decision consumed by the Eval Regression Gate rule.

    The policy intentionally does not create experiments, run evals, compare
    experiments, or mutate ProjectContext. Gate evaluation must remain side
    effect free so StageAdvancementDecision can call it repeatedly.
    """

    dataset_id: str
    status: DecisionStatus
    blocking: bool
    severity: str = "medium"
    required_resolution: str = "run_eval_experiment"
    message: str = ""
    source_type: str = "eval_dataset"
    source_id: str | None = None
    experiment_id: str | None = None
    baseline_experiment_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def dataset_case_hash(case_ids: list[str]) -> str:
    """Stable hash for detecting experiments stale against a dataset case set."""
    payload = json.dumps(sorted(case_ids or []), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_gate_relevant_dataset(dataset: EvalDataset, *, stage: int = 3) -> bool:
    if dataset.stage != stage:
        return False
    tags = {str(tag).lower() for tag in (dataset.tags or [])}
    if tags.intersection(GATE_RELEVANT_TAGS):
        return True
    if dataset.scenario_type in GATE_RELEVANT_SCENARIOS:
        return True
    if dataset.baseline_experiment_id:
        return True
    return bool((dataset.metadata or {}).get("gate_required"))


def gate_relevant_datasets(ctx: ProjectContext, *, stage: int = 3) -> list[EvalDataset]:
    return [
        dataset
        for dataset in getattr(ctx, "eval_datasets", [])
        if is_gate_relevant_dataset(dataset, stage=stage)
    ]


def experiment_by_id(ctx: ProjectContext, experiment_id: str | None) -> EvalExperiment | None:
    if not experiment_id:
        return None
    for experiment in getattr(ctx, "eval_experiments", []):
        if experiment.experiment_id == experiment_id:
            return experiment
    return None


def experiments_for_dataset(ctx: ProjectContext, dataset_id: str) -> list[EvalExperiment]:
    experiments = [
        experiment
        for experiment in getattr(ctx, "eval_experiments", [])
        if experiment.dataset_id == dataset_id
    ]
    return sorted(experiments, key=lambda item: item.created_at, reverse=True)


def latest_current_experiment_for_dataset(
    ctx: ProjectContext,
    dataset: EvalDataset,
) -> EvalExperiment | None:
    for experiment in experiments_for_dataset(ctx, dataset.dataset_id):
        if experiment.experiment_id == dataset.baseline_experiment_id:
            continue
        return experiment
    return None


def experiment_matches_dataset(experiment: EvalExperiment, dataset: EvalDataset) -> bool:
    return sorted(experiment.eval_ids or []) == sorted(dataset.case_ids or [])


def comparison_regression_reasons(comparison: dict[str, Any]) -> list[str]:
    reasons = list(comparison.get("regression_reasons") or [])
    pass_rate_delta = comparison.get("pass_rate_delta")
    critical_delta = comparison.get("critical_fail_count_delta")
    high_delta = comparison.get("high_risk_fail_count_delta")
    parser_delta = comparison.get("parser_failure_count_delta")

    if pass_rate_delta is not None and pass_rate_delta < -EVAL_REGRESSION_MAX_PASS_RATE_DROP:
        if "pass_rate_drop_exceeds_5_percent" not in reasons:
            reasons.append("pass_rate_drop_exceeds_5_percent")
    if critical_delta is not None and critical_delta > EVAL_REGRESSION_MAX_CRITICAL_FAIL_INCREASE:
        if "critical_fail_count_increased" not in reasons:
            reasons.append("critical_fail_count_increased")
    if high_delta is not None and high_delta > EVAL_REGRESSION_MAX_HIGH_RISK_FAIL_INCREASE:
        if "high_risk_fail_count_increased" not in reasons:
            reasons.append("high_risk_fail_count_increased")
    if parser_delta is not None and parser_delta > EVAL_REGRESSION_MAX_PARSER_FAILURE_INCREASE:
        if "parser_failure_count_increased" not in reasons:
            reasons.append("parser_failure_count_increased")
    return reasons


def build_regression_decision(
    ctx: ProjectContext,
    dataset: EvalDataset,
) -> EvalRegressionDecision:
    expected_hash = dataset_case_hash(dataset.case_ids)
    base_metadata: dict[str, Any] = {
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.name,
        "dataset_version": dataset.version,
        "dataset_stage": dataset.stage,
        "dataset_scenario_type": dataset.scenario_type,
        "dataset_case_count": len(dataset.case_ids or []),
        "dataset_case_hash": expected_hash,
        "gate_relevant_tags": sorted(set(dataset.tags or [])),
        "policy_version": APP_VERSION,
        "runtime_validation": "deferred_by_instruction",
    }

    if not is_gate_relevant_dataset(dataset, stage=3):
        return EvalRegressionDecision(
            dataset_id=dataset.dataset_id,
            status="not_gate_relevant",
            blocking=False,
            source_id=dataset.dataset_id,
            metadata=base_metadata,
        )

    if not dataset.case_ids:
        return EvalRegressionDecision(
            dataset_id=dataset.dataset_id,
            status="dataset_empty",
            blocking=True,
            severity="high",
            required_resolution="add_eval_cases_to_dataset",
            message=(
                f"阶段3 gate-relevant EvalDataset {dataset.dataset_id} 没有 case_ids，"
                "必须先补齐可复用 EvalCase；如果 Stage3 已生成 case，可先执行 create_eval_dataset_from_stage3。"
            ),
            source_id=dataset.dataset_id,
            metadata={**base_metadata, "blocking_reason": "dataset_empty"},
        )

    baseline = experiment_by_id(ctx, dataset.baseline_experiment_id)
    if baseline is None:
        return EvalRegressionDecision(
            dataset_id=dataset.dataset_id,
            status="missing_baseline",
            blocking=True,
            severity="high",
            required_resolution="set_eval_baseline",
            message=(
                f"阶段3 gate-relevant EvalDataset {dataset.dataset_id} 缺少 baseline experiment，"
                "不能判断当前版本是否回归。"
            ),
            source_id=dataset.dataset_id,
            metadata={**base_metadata, "blocking_reason": "missing_baseline_experiment"},
        )

    current = latest_current_experiment_for_dataset(ctx, dataset)
    if current is None:
        return EvalRegressionDecision(
            dataset_id=dataset.dataset_id,
            status="missing_current_experiment",
            blocking=True,
            severity="high",
            required_resolution="create_eval_experiment",
            message=(
                f"阶段3 EvalDataset {dataset.dataset_id} 只有 baseline，"
                "缺少用于当前版本推进判断的 EvalExperiment。"
            ),
            source_id=dataset.dataset_id,
            baseline_experiment_id=baseline.experiment_id,
            metadata={**base_metadata, "blocking_reason": "missing_current_experiment"},
        )

    metadata = {
        **base_metadata,
        "baseline_experiment_id": baseline.experiment_id,
        "current_experiment_id": current.experiment_id,
        "current_experiment_status": current.status,
        "current_experiment_eval_ids": list(current.eval_ids or []),
    }

    if current.status != "completed":
        return EvalRegressionDecision(
            dataset_id=dataset.dataset_id,
            status="experiment_not_completed",
            blocking=True,
            severity="high",
            required_resolution="run_eval_experiment",
            message=(
                f"阶段3 EvalExperiment {current.experiment_id} 尚未 completed，"
                "必须完成运行后才能推进。"
            ),
            source_type="eval_experiment",
            source_id=current.experiment_id,
            experiment_id=current.experiment_id,
            baseline_experiment_id=baseline.experiment_id,
            metadata={**metadata, "blocking_reason": "experiment_not_completed"},
        )

    if not experiment_matches_dataset(current, dataset):
        return EvalRegressionDecision(
            dataset_id=dataset.dataset_id,
            status="experiment_stale_for_dataset",
            blocking=True,
            severity="high",
            required_resolution="run_eval_experiment",
            message=(
                f"阶段3 EvalExperiment {current.experiment_id} 的 eval_ids 与 "
                f"EvalDataset {dataset.dataset_id} 当前 case_ids 不一致，需要基于当前 dataset 重新运行。"
            ),
            source_type="eval_experiment",
            source_id=current.experiment_id,
            experiment_id=current.experiment_id,
            baseline_experiment_id=baseline.experiment_id,
            metadata={**metadata, "blocking_reason": "experiment_stale_for_dataset"},
        )

    comparison = dict(current.comparison_summary or {})
    if not comparison:
        return EvalRegressionDecision(
            dataset_id=dataset.dataset_id,
            status="missing_comparison",
            blocking=True,
            severity="high",
            required_resolution="compare_eval_experiment",
            message=(
                f"阶段3 EvalExperiment {current.experiment_id} 已完成，但尚未与 baseline "
                f"{baseline.experiment_id} 生成 comparison_summary。"
            ),
            source_type="eval_experiment",
            source_id=current.experiment_id,
            experiment_id=current.experiment_id,
            baseline_experiment_id=baseline.experiment_id,
            metadata={**metadata, "blocking_reason": "missing_comparison"},
        )

    reasons = comparison_regression_reasons(comparison)
    regression_detected = bool(comparison.get("regression_detected")) or bool(reasons)
    if regression_detected:
        return EvalRegressionDecision(
            dataset_id=dataset.dataset_id,
            status="regression_detected",
            blocking=True,
            severity="critical" if comparison.get("critical_fail_count_delta", 0) > 0 else "high",
            required_resolution="revise_stage",
            message=(
                f"阶段3 EvalExperiment {current.experiment_id} 相比 baseline "
                f"{baseline.experiment_id} 出现回归，不能进入下一阶段。"
            ),
            source_type="eval_experiment",
            source_id=current.experiment_id,
            experiment_id=current.experiment_id,
            baseline_experiment_id=baseline.experiment_id,
            metadata={
                **metadata,
                "blocking_reason": "regression_detected",
                "comparison_summary": comparison,
                "regression_reasons": reasons,
                "gate_effect": "blocks_stage_advancement_in_v0.8_alpha2",
            },
        )

    return EvalRegressionDecision(
        dataset_id=dataset.dataset_id,
        status="passed",
        blocking=False,
        severity="low",
        required_resolution="compare_eval_experiment",
        message=(
            f"阶段3 EvalDataset {dataset.dataset_id} 的最新 EvalExperiment "
            f"{current.experiment_id} 未检测到回归。"
        ),
        source_type="eval_experiment",
        source_id=current.experiment_id,
        experiment_id=current.experiment_id,
        baseline_experiment_id=baseline.experiment_id,
        metadata={
            **metadata,
            "comparison_summary": comparison,
            "gate_effect": "passed_stage_advancement_in_v0.8_alpha2",
        },
    )


def build_stage_regression_decisions(
    ctx: ProjectContext,
    *,
    stage: int = 3,
) -> list[EvalRegressionDecision]:
    return [
        build_regression_decision(ctx, dataset)
        for dataset in gate_relevant_datasets(ctx, stage=stage)
    ]


def build_stage_eval_regression_summary(ctx: ProjectContext, *, stage: int = 3) -> dict[str, Any]:
    decisions = build_stage_regression_decisions(ctx, stage=stage)
    blocking = [decision for decision in decisions if decision.blocking]
    return {
        "stage": stage,
        "policy_version": APP_VERSION,
        "runtime_validation": "deferred_by_instruction",
        "gate_relevant_dataset_count": len(decisions),
        "blocking_dataset_count": len(blocking),
        "blocking_status_counts": {
            status: len([decision for decision in blocking if decision.status == status])
            for status in sorted({decision.status for decision in blocking})
        },
        "passed_dataset_count": len(
            [decision for decision in decisions if decision.status == "passed"]
        ),
        "decisions": [
            {
                "dataset_id": decision.dataset_id,
                "status": decision.status,
                "blocking": decision.blocking,
                "severity": decision.severity,
                "required_resolution": decision.required_resolution,
                "source_type": decision.source_type,
                "source_id": decision.source_id,
                "experiment_id": decision.experiment_id,
                "baseline_experiment_id": decision.baseline_experiment_id,
                "message": decision.message,
                "metadata": decision.metadata,
            }
            for decision in decisions
        ],
    }
