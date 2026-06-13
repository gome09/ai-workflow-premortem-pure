# core/llm/adapters/openai_compatible.py
from __future__ import annotations

from dataclasses import dataclass

from core.llm.provider import StructuredGenerationRequest, StructuredGenerationResponse


@dataclass
class OpenAICompatibleStructuredOutputProvider:
    """OpenAI-compatible boundary placeholder.

    This class intentionally does not perform network calls in the
    v0.7-alpha.3 source patch. The live integration should be completed and
    validated during the later unified provider-validation pass.
    """

    provider_name: str = "openai_compatible"
    supports_native_schema: bool = False

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResponse:
        raise NotImplementedError(
            "OpenAI-compatible structured generation is deferred until unified runtime validation."
        )
