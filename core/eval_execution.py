# core/eval_execution.py
"""Bounded in-process executor for long EvalExperiment batches.

This is deliberately not a general task queue: it only prevents a long
synchronous HTTP request from being killed by client/proxy timeouts. Durable
progress lives in the project context and can be resumed after a process
restart; the thread pool itself is process-local and disposable.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_executor: ThreadPoolExecutor | None = None
_futures: dict[str, Future[None]] = {}
_request_keys: dict[str, str] = {}


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, int(settings.eval_experiment_workers)),
                thread_name_prefix="eval-experiment",
            )
        return _executor


def submit_eval_experiment(
    key: str, job: Callable[[], None], *, request_key: str = ""
) -> tuple[Future[None], bool]:
    """Submit one experiment job; duplicate keys reuse the in-flight future.

    Returns ``(future, created)`` so callers can distinguish a new submission
    from an idempotent duplicate without racing on the persisted status.
    """
    with _lock:
        existing = _futures.get(key)
        if existing is not None and not existing.done():
            return existing, False
        future = _get_executor().submit(job)
        _futures[key] = future
        _request_keys[key] = request_key

    def _cleanup(_future: Future[None]) -> None:
        with _lock:
            if _futures.get(key) is future:
                _futures.pop(key, None)
                _request_keys.pop(key, None)

    future.add_done_callback(_cleanup)
    return future, True


def in_flight_request_key(key: str) -> str | None:
    """Return the request key of the in-flight job, or ``None`` when idle."""
    with _lock:
        future = _futures.get(key)
        if future is None or future.done():
            return None
        return _request_keys.get(key, "")


def shutdown_eval_executor() -> None:
    global _executor
    with _lock:
        executor = _executor
        _executor = None
        _futures.clear()
        _request_keys.clear()
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)
        logger.info("eval experiment executor shutdown")
