# core/llm/adapters/openai_compatible.py
from __future__ import annotations

from dataclasses import dataclass

from core.llm.provider import StructuredGenerationRequest, StructuredGenerationResponse


@dataclass
class OpenAICompatibleStructuredOutputProvider:
    """OpenAI-compatible boundary placeholder.

    This class is a stub. Network calls are not implemented; the live integration
    requires a unified provider-validation pass before it can be used in production.
    """

    provider_name: str = "openai_compatible"
    supports_native_schema: bool = False

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResponse:
        raise NotImplementedError(
            "OpenAI-compatible structured generation is deferred until unified runtime validation."
        )
