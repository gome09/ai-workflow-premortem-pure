# storage/eval_claim.py
"""Shared claim/lease value objects for EvalExperiment coordination.

The coordination columns live on ``eval_experiments`` and are written only by
the storage layer's claim/heartbeat/progress/recover transactions. Projection
sync never touches them, so an ordinary ``save()`` cannot silently steal or
extend a lease.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ClaimReason = Literal[
    "claimed",
    "already_running",
    "request_key_mismatch",
    "completed",
    "not_found",
]


@dataclass(frozen=True)
class EvalClaim:
    """Current coordination state of one experiment (owner excluded from API)."""

    owner: str
    attempt: int
    request_key: str
    heartbeat_at: datetime | None
    lease_until: datetime | None


@dataclass(frozen=True)
class EvalClaimOutcome:
    """Result of a claim attempt made inside the storage transaction."""

    claimed: bool
    reason: ClaimReason
    claim: EvalClaim | None = None
