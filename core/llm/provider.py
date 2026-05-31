# core/llm/provider.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class StructuredGenerationRequest:
    """Provider-neutral request for schema-bound stage output generation."""

    stage: int
    prompt: str = ""
    messages: list[Any] = field(default_factory=list)
    output_schema: type | None = None
    model: str = ""
    temperature: float = 0.0
    max_retries: int = 0
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredGenerationResponse:
    """Provider-neutral raw response before project schema validation."""

    raw_text: str
    provider: str
    model: str = ""
    retry_count: int = 0
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class StructuredOutputProvider(Protocol):
    """Boundary implemented by concrete LLM adapters.

    Adapters may use native JSON/schema modes when available, or return raw
    text for the existing parser path. Stage executors must continue to
    validate through StructuredOutputClient.
    """

    provider_name: str
    supports_native_schema: bool

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResponse: ...
