# core/eval_experiment_service.py
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from core.audit_service import append_audit_event
from core.eval_comparison_service import compare_experiments
from core.eval_dataset_service import get_dataset
from core.eval_metrics_service import compute_experiment_metrics
from core.eval_runner import run_eval_cases
from core.models import EvalExperiment, ProjectContext
from core.traces import append_llm_trace, create_llm_trace
from core.version import APP_VERSION


def _hash_config(value: dict[str, Any]) -> str:
    data = json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _get_experiment(ctx: ProjectContext, experiment_id: str) -> EvalExperiment:
    for experiment in ctx.eval_experiments:
        if experiment.experiment_id == experiment_id:
            return experiment
    raise ValueError(f"Eval experiment not found: {experiment_id}")


def _trace_experiment_event(
    ctx: ProjectContext,
    experiment: EvalExperiment,
    event_kind: str,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    trace = create_llm_trace(
        ctx,
        stage=3,
        node_name=event_kind,
        trace_type="eval",
        parser_status="not_applicable",
        provider=experiment.provider or "",
        model=experiment.model or "",
        metadata={
            "event_kind": event_kind,
            "dataset_id": experiment.dataset_id,
            "experiment_id": experiment.experiment_id,
            "status": experiment.status,
            "run_mode": experiment.run_mode,
            "run_count": len(experiment.run_ids),
            "eval_count": len(experiment.eval_ids),
            "baseline_experiment_id": experiment.baseline_experiment_id,
            "runtime_validation": "deferred_by_instruction",
            **(extra or {}),
        },
    )
    append_llm_trace(ctx, trace)


def list_experiments(ctx: ProjectContext) -> list[EvalExperiment]:
    return list(ctx.eval_experiments)


def get_experiment(ctx: ProjectContext, experiment_id: str) -> EvalExperiment:
    return _get_experiment(ctx, experiment_id)


def create_experiment(
    ctx: ProjectContext,
    *,
    dataset_id: str,
    name: str,
    description: str = "",
    run_mode: str = "manual",
    provider: str | None = None,
    model: str | None = None,
    baseline_experiment_id: str | None = None,
    run_config: dict[str, Any] | None = None,
    created_by: str = "system",
) -> EvalExperiment:
    dataset = get_dataset(ctx, dataset_id)
    if baseline_experiment_id is None:
        baseline_experiment_id = dataset.baseline_experiment_id
    if baseline_experiment_id is not None:
        _get_experiment(ctx, baseline_experiment_id)

    config = run_config or {}
    experiment = EvalExperiment(
        session_id=ctx.session_id,
        dataset_id=dataset.dataset_id,
        name=name,
        description=description,
        run_mode=run_mode,  # type: ignore[arg-type]
        provider=provider,
        model=model,
        baseline_experiment_id=baseline_experiment_id,
        run_config=config,
        run_config_hash=_hash_config(config),
        eval_ids=list(dataset.case_ids),
        code_version=APP_VERSION,
        created_by=created_by,
    )
    ctx.eval_experiments.append(experiment)
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_experiment_created",
        target_type="eval_experiment",
        target_id=experiment.experiment_id,
        after=experiment,
        metadata={
            "dataset_id": dataset.dataset_id,
            "case_count": len(experiment.eval_ids),
            "run_mode": experiment.run_mode,
            "baseline_experiment_id": experiment.baseline_experiment_id,
        },
    )
    _trace_experiment_event(ctx, experiment, "eval_experiment_created")
    return experiment


def run_experiment(
    ctx: ProjectContext, *, experiment_id: str, dry_run_only: bool = True
) -> EvalExperiment:
    experiment = _get_experiment(ctx, experiment_id)
    if experiment.status == "completed":
        raise ValueError(
            "EvalExperiment is already completed; create a new experiment for a new comparison."
        )
    dataset = get_dataset(ctx, experiment.dataset_id)
    if not dataset.case_ids:
        raise ValueError(f"Eval dataset has no cases: {dataset.dataset_id}")

    before = experiment.model_copy(deep=True)
    experiment.status = "running"
    experiment.started_at = datetime.utcnow()
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_experiment_started",
        target_type="eval_experiment",
        target_id=experiment.experiment_id,
        before=before,
        after=experiment,
        metadata={"dry_run_only": dry_run_only},
    )
    _trace_experiment_event(ctx, experiment, "eval_experiment_started")

    requested_run_mode = experiment.run_mode
    actual_run_mode = (
        "dry_run" if dry_run_only and requested_run_mode == "llm_node" else requested_run_mode
    )

    try:
        runs = run_eval_cases(
            ctx,
            eval_ids=dataset.case_ids,
            run_mode=actual_run_mode,
            dataset_id=dataset.dataset_id,
            experiment_id=experiment.experiment_id,
        )
        experiment.run_ids = [run.run_id for run in runs]
        experiment.eval_ids = list(dataset.case_ids)
        experiment.status = "completed"
        experiment.completed_at = datetime.utcnow()
        metrics = compute_experiment_metrics(ctx, experiment_id=experiment.experiment_id)
        if experiment.baseline_experiment_id:
            compare_experiments(
                ctx,
                current_experiment_id=experiment.experiment_id,
                baseline_experiment_id=experiment.baseline_experiment_id,
            )
        append_audit_event(
            ctx,
            actor="system",
            event_type="eval_experiment_completed",
            target_type="eval_experiment",
            target_id=experiment.experiment_id,
            before=before,
            after=experiment,
            metadata={
                "dataset_id": dataset.dataset_id,
                "run_count": len(experiment.run_ids),
                "pass_rate": metrics.pass_rate,
                "dry_run_only": dry_run_only,
                "actual_run_mode": actual_run_mode,
                "gate_effect": "eval_regression_rule_consumes_comparison_in_v0.8_alpha2",
            },
        )
        _trace_experiment_event(
            ctx,
            experiment,
            "eval_experiment_completed",
            extra={
                "pass_rate": metrics.pass_rate,
                "fail_count": metrics.fail_count,
                "needs_review_count": metrics.needs_review_count,
                "regression_detected": experiment.comparison_summary.get("regression_detected"),
                "actual_run_mode": actual_run_mode,
            },
        )
        return experiment
    except Exception as exc:  # noqa: BLE001
        experiment.status = "failed"
        experiment.completed_at = datetime.utcnow()
        append_audit_event(
            ctx,
            actor="system",
            event_type="eval_experiment_failed",
            target_type="eval_experiment",
            target_id=experiment.experiment_id,
            before=before,
            after=experiment,
            metadata={"error_message": str(exc), "dry_run_only": dry_run_only},
        )
        _trace_experiment_event(
            ctx,
            experiment,
            "eval_experiment_failed",
            extra={"error_message": str(exc)},
        )
        raise


def get_experiment_metrics(ctx: ProjectContext, *, experiment_id: str):
    return compute_experiment_metrics(ctx, experiment_id=experiment_id)


def compare_experiment_with_baseline(
    ctx: ProjectContext,
    *,
    experiment_id: str,
    baseline_experiment_id: str | None = None,
) -> dict:
    experiment = _get_experiment(ctx, experiment_id)
    baseline_id = baseline_experiment_id or experiment.baseline_experiment_id
    if not baseline_id:
        raise ValueError("baseline_experiment_id is required")
    comparison = compare_experiments(
        ctx,
        current_experiment_id=experiment_id,
        baseline_experiment_id=baseline_id,
    )
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_experiment_compared",
        target_type="eval_experiment",
        target_id=experiment.experiment_id,
        after=experiment,
        metadata=comparison,
    )
    _trace_experiment_event(ctx, experiment, "eval_experiment_compared", extra=comparison)
    return comparison
