# core/eval_heartbeat.py
"""Lease heartbeat for one claimed EvalExperiment background/sync run."""

from __future__ import annotations

import logging
import threading

from core.config import settings
from storage.errors import EvalClaimLostError
from storage.eval_claim import EvalClaim

logger = logging.getLogger(__name__)


class EvalLeaseHeartbeat:
    """Refresh ``claim_lease_until`` while the owning worker is still executing.

    The heartbeat never advances the context version, writes audit events or
    clears the cache: it only extends the coordination lease.
    """

    def __init__(
        self,
        store,
        session_id: str,
        tenant_id: str,
        experiment_id: str,
        claim: EvalClaim,
        *,
        interval_seconds: int | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        self._store = store
        self._session_id = session_id
        self._tenant_id = tenant_id
        self._experiment_id = experiment_id
        self._claim = claim
        self._lease_seconds = int(lease_seconds or settings.eval_experiment_lease_seconds)
        self._interval = int(
            interval_seconds or settings.eval_experiment_heartbeat_interval_seconds
        )
        self._lost = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"eval-heartbeat-{self._experiment_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=max(1.0, float(self._interval)))

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                alive = self._store.heartbeat_eval_experiment(
                    self._session_id,
                    self._tenant_id,
                    self._experiment_id,
                    self._claim.owner,
                    self._claim.attempt,
                    self._lease_seconds,
                )
            except Exception:  # noqa: BLE001 - a failed heartbeat means stop the batch
                logger.exception(
                    "eval_experiment_heartbeat_failed",
                    extra={"experiment_id": self._experiment_id},
                )
                self._lost.set()
                return
            if not alive:
                self._lost.set()
                return

    def verify(self) -> None:
        """Fail closed before every external call; DB is the source of truth."""
        if self._lost.is_set():
            raise EvalClaimLostError(self._experiment_id, "heartbeat_lost")
        try:
            alive = self._store.verify_eval_experiment_owner(
                self._session_id,
                self._tenant_id,
                self._experiment_id,
                self._claim.owner,
                self._claim.attempt,
            )
        except Exception as exc:  # noqa: BLE001 - storage errors mean no ownership proof
            raise EvalClaimLostError(self._experiment_id, "verify_failed") from exc
        if not alive:
            self._lost.set()
            raise EvalClaimLostError(self._experiment_id, "lease_expired")
