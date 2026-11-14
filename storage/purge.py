"""Shared purge result types for both storage backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PurgeReason = Literal["deleted", "stale", "not_found"]


@dataclass(frozen=True)
class PurgeOutcome:
    """Outcome of one session purge attempt.

    ``deleted`` is true only when the parent session row was actually removed in
    the same transaction that archived its audit events. ``stale`` means the
    retention candidate no longer satisfies the cutoff; ``not_found`` means the
    tenant-scoped parent row did not exist.
    """

    deleted: bool
    archived_events: int = 0
    reason: PurgeReason = "deleted"
