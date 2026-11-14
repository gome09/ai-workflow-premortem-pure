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
    """Another runner owns the experiment, or the request key does not match."""

    def __init__(self, experiment_id: str, reason: str = "already_running") -> None:
        self.experiment_id = experiment_id
        self.reason = reason
        super().__init__(f"EvalExperiment is already running or claimed: {experiment_id}")


@dataclass(frozen=True)
class ClaimDecision:
    """Outcome of a claim decision evaluated under the storage write lock."""

    claimed: bool
    reason: str
    attempt: int = 0


def new_claim_owner() -> str:
    """Opaque per-run owner token; never contains host or user information."""
    return uuid.uuid4().hex


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

    before = experiment.model_copy(deep=True)
    attempt = max(int(experiment.execution_attempt or 0), int(coordination_attempt or 0)) + 1
    if experiment.started_at is None:
        experiment.started_at = now
    experiment.status = "running"
    experiment.run_request_key = request_key or persisted_key
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
