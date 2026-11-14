# core/eval_claim.py
"""Business rules for claiming an EvalExperiment in the database.

The storage layer owns the transaction/lock and calls :func:`begin_claim`
inside it; this module only decides whether the claim is legal and mutates the
loaded context accordingly. Keeping the decision here means PostgreSQL and
SQLite cannot drift apart on status/request-key semantics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from core.audit_service import append_audit_event
from core.config import settings
from core.eval_experiment_events import trace_experiment_event
from core.models import EvalExperiment, ProjectContext


class EvalClaimConflictError(ValueError):
    """Another runner owns the experiment, or the request key/mode does not match."""

    def __init__(self, experiment_id: str, reason: str = "already_running") -> None:
        self.experiment_id = experiment_id
        self.reason = reason
        if reason == "execution_mode_mismatch":
            message = (
                "EvalExperiment was already executed with a different mode; "
                "create a new experiment instead of resuming it"
            )
        else:
            message = f"EvalExperiment is already running or claimed: {experiment_id}"
        super().__init__(message)


@dataclass(frozen=True)
class ClaimDecision:
    """Outcome of a claim decision evaluated under the storage write lock."""

    claimed: bool
    reason: str
    attempt: int = 0


def new_claim_owner() -> str:
    """Opaque per-run owner token; never contains host or user information."""
    return uuid.uuid4().hex


def actual_execution_mode(experiment: EvalExperiment, dry_run_only: bool) -> str:
    """Return the mode this attempt will actually execute."""
    if dry_run_only and experiment.run_mode in {"llm_node", "target_http"}:
        return "dry_run"
    return experiment.run_mode


def infer_execution_mode(ctx: ProjectContext, experiment: EvalExperiment) -> tuple[str, bool]:
    """Infer the persisted execution mode for experiments created before this field.

    Returns ``(mode, inferred)``. ``mixed`` means the experiment already contains
    runs with different modes and cannot be resumed without creating a new one.
    """
    if experiment.execution_mode:
        return experiment.execution_mode, False
    modes = {
        run.run_mode
        for run in ctx.eval_runs
        if run.experiment_id == experiment.experiment_id and run.run_mode
    }
    if not modes:
        return "", False
    if len(modes) == 1:
        return next(iter(modes)), True
    return "mixed", True


def _find_experiment(ctx: ProjectContext, experiment_id: str) -> EvalExperiment | None:
    for experiment in ctx.eval_experiments:
        if experiment.experiment_id == experiment_id:
            return experiment
    return None


def begin_claim(
    ctx: ProjectContext,
    experiment_id: str,
    *,
    owner: str,
    request_key: str,
    timeout_seconds: int | None,
    coordination_attempt: int,
    now: datetime,
    dry_run_only: bool = True,
) -> ClaimDecision:
    """Decide and apply a claim on the already-locked context.

    ``coordination_attempt`` is the persisted ``claim_attempt`` column, so a
    stale context can never lower the attempt counter. Returns ``claimed=False``
    without touching the context when the experiment is not claimable.
    """
    experiment = _find_experiment(ctx, experiment_id)
    if experiment is None:
        return ClaimDecision(False, "not_found")

    persisted_key = experiment.run_request_key or ""
    if experiment.status == "completed":
        if not request_key or persisted_key == request_key:
            return ClaimDecision(False, "completed")
        return ClaimDecision(False, "request_key_mismatch")
    if experiment.status == "running":
        if request_key and persisted_key == request_key:
            return ClaimDecision(False, "already_running")
        return ClaimDecision(False, "request_key_mismatch")
    if request_key and persisted_key and persisted_key != request_key:
        return ClaimDecision(False, "request_key_mismatch")

    requested_mode = actual_execution_mode(experiment, dry_run_only)
    previous_mode, _inferred = infer_execution_mode(ctx, experiment)
    if previous_mode and previous_mode != requested_mode:
        return ClaimDecision(False, "execution_mode_mismatch")

    before = experiment.model_copy(deep=True)
    attempt = max(int(experiment.execution_attempt or 0), int(coordination_attempt or 0)) + 1
    if experiment.started_at is None:
        experiment.started_at = now
    experiment.status = "running"
    experiment.run_request_key = request_key or persisted_key
    experiment.execution_mode = requested_mode
    experiment.execution_attempt = attempt
    experiment.last_heartbeat_at = now
    experiment.completed_at = None
    experiment.last_error_code = ""
    experiment.timeout_seconds = int(
        timeout_seconds or experiment.timeout_seconds or settings.eval_experiment_timeout_seconds
    )
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_experiment_started",
        target_type="eval_experiment",
        target_id=experiment.experiment_id,
        before=before,
        after=experiment,
        metadata={
            "request_key": experiment.run_request_key,
            "attempt": attempt,
            "timeout_seconds": experiment.timeout_seconds,
            "execution_mode": experiment.execution_mode,
        },
    )
    trace_experiment_event(ctx, experiment, "eval_experiment_started")
    return ClaimDecision(True, "claimed", attempt)


def recover_lease(
    ctx: ProjectContext,
    experiment_id: str,
    *,
    now: datetime,
    error_code: str = "lease_expired",
) -> bool:
    """Mark a lease-expired running experiment interrupted; return whether it changed."""
    experiment = _find_experiment(ctx, experiment_id)
    if experiment is None or experiment.status != "running":
        return False
    before = experiment.model_copy(deep=True)
    experiment.status = "interrupted"
    experiment.last_error_code = error_code
    experiment.completed_at = now
    experiment.last_heartbeat_at = now
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_experiment_interrupted",
        target_type="eval_experiment",
        target_id=experiment.experiment_id,
        before=before,
        after=experiment,
        metadata={
            "reason": error_code,
            "request_key": experiment.run_request_key,
            "attempt": experiment.execution_attempt,
        },
    )
    trace_experiment_event(
        ctx,
        experiment,
        "eval_experiment_interrupted",
        extra={"error_code": error_code, "attempt": experiment.execution_attempt},
    )
    return True
