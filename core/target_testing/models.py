# core/target_testing/models.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TargetExecutionOutcome = Literal["success", "failed", "timeout", "error"]


class TargetSystemConfig(BaseModel):
    """Minimal HTTP JSON contract for a real target system.

    The target receives a JSON body with ``input`` (plus correlation ids) and
    must return a JSON object containing ``output_field``.
    """

    endpoint: str
    timeout_seconds: float = Field(default=10.0, gt=0)
    output_field: str = "output"


class TargetTestResponse(BaseModel):
    """One real-target execution result. Raw response body is never stored."""

    outcome: TargetExecutionOutcome
    output: str = ""
    status_code: int | None = None
    latency_ms: int | None = None
    error_code: str = ""
    error_message: str = ""
    endpoint: str = ""
    response_digest: str = ""
    truncated: bool = False
