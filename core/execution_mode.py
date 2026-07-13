# core/execution_mode.py
from __future__ import annotations

from enum import StrEnum


class WorkflowExecutionMode(StrEnum):
    SINGLE_STEP = "single_step"
    LANGGRAPH_INTERRUPT = "langgraph_interrupt"

    @classmethod
    def normalize(cls, value: str | WorkflowExecutionMode) -> WorkflowExecutionMode:
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError as exc:
            allowed = ", ".join(mode.value for mode in cls)
            raise ValueError(
                f"Unsupported workflow_execution_mode={value!r}; allowed: {allowed}"
            ) from exc
