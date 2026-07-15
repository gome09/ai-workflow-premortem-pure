# core/llm/retry.py
from __future__ import annotations

from dataclasses import dataclass

RETRYABLE_PARSER_STATUSES = {"non_json", "validation_failed", "retry_exhausted"}


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry policy for structured-output generation."""

    max_retries: int = 1
    retry_on: set[str] | None = None

    def should_retry(self, parser_status: str, attempt: int) -> bool:
        statuses = self.retry_on or RETRYABLE_PARSER_STATUSES
        return attempt < self.max_retries and parser_status in statuses


def bounded_retry_plan(max_retries: int) -> list[int]:
    """Return attempt numbers including the first attempt.

    `max_retries=0` returns `[0]`; `max_retries=2` returns `[0, 1, 2]`.
    """
    return list(range(max(0, max_retries) + 1))
