# core/eval_experiment_service.py
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from core.audit_service import append_audit_event
from core.config import settings
from core.eval_comparison_service import compare_experiments
from core.eval_dataset_service import get_dataset
from core.eval_metrics_service import compute_experiment_metrics
from core.eval_runner import run_eval_case
from core.evaluation_version import current_evaluation_digest, eval_case_digest
from core.models import EvalExperiment, EvalRun, ProjectContext
from core.traces import append_llm_trace, create_llm_trace
from core.version import APP_VERSION

logger = logging.getLogger(__name__)


class EvalExperimentTimeoutError(ValueError):
    """The experiment-wide deadline expired before all cases completed."""


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


def _run_idempotency_key(
    ctx: ProjectContext,
    experiment: EvalExperiment,
    eval_id: str,
    *,
    run_mode: str,
) -> str:
    case = next((item for item in ctx.eval_cases if item.eval_id == eval_id), None)
    digest = current_evaluation_digest(ctx)
    case_digest = eval_case_digest(case) if case is not None else ""
    target_version = ctx.target_deployment.version if ctx.target_deployment is not None else ""
    raw = (
        f"eval-exp:{experiment.experiment_id}:{eval_id}:{run_mode}:"
        f"{digest}:{case_digest}:{target_version}"
    )
    return "eval-exp:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finished_eval_ids(ctx: ProjectContext, experiment: EvalExperiment) -> set[str]:
    """Cases whose result was already persisted; resume must not re-execute them."""
    return {
        run.eval_id
        for run in ctx.eval_runs
        if run.experiment_id == experiment.experiment_id and run.status in {"completed", "failed"}
    }


def _append_unique(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


def run_experiment(
    ctx: ProjectContext,
    *,
    experiment_id: str,
    dry_run_only: bool = True,
    request_key: str = "",
    timeout_seconds: int | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> EvalExperiment:
    """Run or resume one experiment with per-item persistence and idempotent retry."""
    experiment = _get_experiment(ctx, experiment_id)
    if experiment.status == "completed":
        if request_key and experiment.run_request_key == request_key:
            return experiment
        raise ValueError(
            "EvalExperiment is already completed; create a new experiment for a new comparison."
        )
    if experiment.status == "running":
        raise ValueError("EvalExperiment is already running")
    if request_key and experiment.run_request_key and experiment.run_request_key != request_key:
        raise ValueError("EvalExperiment request key does not match the persisted run")

    dataset = get_dataset(ctx, experiment.dataset_id)
    if not dataset.case_ids:
        raise ValueError(f"Eval dataset has no cases: {dataset.dataset_id}")
    if experiment.run_mode == "target_http" and not dry_run_only:
        raw_config = (experiment.run_config or {}).get("target_config")
        if not isinstance(raw_config, dict) or not raw_config.get("endpoint"):
            raise ValueError("target_http experiment requires run_config.target_config")

    before = experiment.model_copy(deep=True)
    now = datetime.utcnow()
    if experiment.started_at is None:
        experiment.started_at = now
    experiment.status = "running"
    experiment.run_request_key = request_key or experiment.run_request_key
    experiment.execution_attempt += 1
    experiment.last_heartbeat_at = now
    experiment.completed_at = None
    experiment.last_error_code = ""
    experiment.timeout_seconds = int(
        timeout_seconds or experiment.timeout_seconds or settings.eval_experiment_timeout_seconds
    )
    deadline = now + timedelta(seconds=experiment.timeout_seconds)
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_experiment_started",
        target_type="eval_experiment",
        target_id=experiment.experiment_id,
        before=before,
        after=experiment,
        metadata={
            "dry_run_only": dry_run_only,
            "request_key": experiment.run_request_key,
            "attempt": experiment.execution_attempt,
            "timeout_seconds": experiment.timeout_seconds,
        },
    )
    _trace_experiment_event(ctx, experiment, "eval_experiment_started")

    requested_run_mode = experiment.run_mode
    actual_run_mode = (
        "dry_run"
        if dry_run_only and requested_run_mode in {"llm_node", "target_http"}
        else requested_run_mode
    )

    from core.target_testing import TargetSystemConfig

    raw_target_config = (experiment.run_config or {}).get("target_config")
    target_config = (
        TargetSystemConfig.model_validate(raw_target_config)
        if isinstance(raw_target_config, dict)
        else None
    )
    finished_eval_ids = _finished_eval_ids(ctx, experiment)
    experiment.eval_ids = list(dataset.case_ids)

    def _safe_notify() -> None:
        if progress_callback is None:
            return
        try:
            progress_callback()
        except Exception as exc:  # noqa: BLE001 - preserve the original execution error
            # 版本冲突必须中止批次：继续执行会产生无法保存的外部调用。
            if type(exc).__name__ == "StaleContextError":
                raise
            logger.exception("eval experiment progress callback failed")

    try:
        for index, eval_id in enumerate(dataset.case_ids):
            if eval_id in finished_eval_ids:
                continue
            if datetime.utcnow() >= deadline:
                raise EvalExperimentTimeoutError(
                    f"EvalExperiment {experiment.experiment_id} exceeded "
                    f"{experiment.timeout_seconds} seconds"
                )
            run: EvalRun = run_eval_case(
                ctx,
                eval_id=eval_id,
                run_mode=actual_run_mode,
                dataset_id=dataset.dataset_id,
                experiment_id=experiment.experiment_id,
                run_index=index,
                target_config=target_config,
                idempotency_key=_run_idempotency_key(
                    ctx,
                    experiment,
                    eval_id,
                    run_mode=actual_run_mode,
                ),
            )
            _append_unique(experiment.run_ids, run.run_id)
            experiment.last_heartbeat_at = datetime.utcnow()
            if progress_callback is not None:
                progress_callback()

        experiment.status = "completed"
        experiment.completed_at = datetime.utcnow()
        experiment.last_heartbeat_at = experiment.completed_at
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
                "request_key": experiment.run_request_key,
                "attempt": experiment.execution_attempt,
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
                "attempt": experiment.execution_attempt,
            },
        )
        if progress_callback is not None:
            progress_callback()
        return experiment
    except Exception as exc:  # noqa: BLE001 - failed eval experiments must be auditable
        if isinstance(exc, EvalExperimentTimeoutError):
            experiment.last_error_code = "experiment_timeout"
        elif type(exc).__name__ == "StaleContextError":
            experiment.last_error_code = "stale_context"
        else:
            experiment.last_error_code = "experiment_error"
        experiment.status = (
            "interrupted" if experiment.last_error_code == "stale_context" else "failed"
        )
        experiment.completed_at = datetime.utcnow()
        experiment.last_heartbeat_at = experiment.completed_at
        append_audit_event(
            ctx,
            actor="system",
            event_type="eval_experiment_failed",
            target_type="eval_experiment",
            target_id=experiment.experiment_id,
            before=before,
            after=experiment,
            metadata={
                "error_message": str(exc)[:500],
                "error_code": experiment.last_error_code,
                "dry_run_only": dry_run_only,
                "request_key": experiment.run_request_key,
                "attempt": experiment.execution_attempt,
            },
        )
        _trace_experiment_event(
            ctx,
            experiment,
            "eval_experiment_failed",
            extra={
                "error_message": str(exc)[:500],
                "error_code": experiment.last_error_code,
                "attempt": experiment.execution_attempt,
            },
        )
        _safe_notify()
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
