# core/eval_experiment_events.py
"""Shared audit-trace helper for EvalExperiment lifecycle events.

Kept in its own module so both ``eval_experiment_service`` (run/completion) and
``eval_claim`` (claim/interrupt) can emit traces without importing each other.
"""

from __future__ import annotations

from typing import Any

from core.models import EvalExperiment, ProjectContext
from core.traces import append_llm_trace, create_llm_trace


def trace_experiment_event(
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
