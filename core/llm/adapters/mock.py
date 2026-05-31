# core/llm/adapters/mock.py
from __future__ import annotations

from dataclasses import dataclass

from core.llm.provider import StructuredGenerationRequest, StructuredGenerationResponse


@dataclass
class MockStructuredOutputProvider:
    """Deterministic provider for later unit tests and offline validation."""

    raw_text: str
    provider_name: str = "mock"
    supports_native_schema: bool = True

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResponse:
        return StructuredGenerationResponse(
            raw_text=self.raw_text,
            provider=self.provider_name,
            model=request.model or "mock-model",
            retry_count=0,
            trace_id=request.trace_id,
            metadata={
                "stage": request.stage,
                "supports_native_schema": self.supports_native_schema,
                "offline_mock": True,
            },
        )
