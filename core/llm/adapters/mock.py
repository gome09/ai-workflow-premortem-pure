# core/llm/adapters/mock.py
"""Mock LLM adapter for demo mode and offline CI testing.

Returns deterministic per-stage, per-profile fixture JSON that passes the
existing json_first parser without any network calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.llm.provider import StructuredGenerationRequest, StructuredGenerationResponse
from core.scenario_context import current_mock_fixture

_PROFILE_MODULES = {
    "default": "core.llm.adapters.mock_fixtures.default",
    "university_ai": "core.llm.adapters.mock_fixtures.university_ai",
    "medical_ai": "core.llm.adapters.mock_fixtures.medical_ai",
}

_STAGE_FUNCTIONS = {
    1: "stage_1_response",
    2: "stage_2_response",
    3: "stage_3_response",
    4: "stage_4_response",
}


def _resolve_module_path(fixture_name: str) -> str:
    if fixture_name in _PROFILE_MODULES:
        return _PROFILE_MODULES[fixture_name]
    if "." in fixture_name:
        return fixture_name
    return f"core.llm.adapters.mock_fixtures.{fixture_name}"


def _get_fixture_json(stage: int, domain_profile: str, ctx: Any | None = None) -> str:
    """Return fixture JSON string for the given stage and domain profile."""
    import importlib

    fixture_name = current_mock_fixture(ctx) if ctx is not None else domain_profile
    module_path = _resolve_module_path(fixture_name or domain_profile or "default")
    if stage not in _STAGE_FUNCTIONS:
        raise ValueError(
            f"No mock fixture for stage {stage}. Valid stages: {list(_STAGE_FUNCTIONS)}"
        )
    func_name = _STAGE_FUNCTIONS[stage]
    module = importlib.import_module(module_path)
    return getattr(module, func_name)()


class _FakeInvokeResponse:
    """Minimal duck-type of a LangChain AIMessage for the mock invoke path."""

    def __init__(self, content: str) -> None:
        self.content = content


class MockLLMAdapter:
    """LangChain-compatible mock adapter that returns fixture JSON without any network calls.

    Implements both the LangChain invoke() interface (used by BaseStageExecutor)
    and the StructuredOutputProvider generate_structured() interface (used in tests
    and StructuredOutputClient.generate()).
    """

    provider_name: str = "mock"
    supports_native_schema: bool = True
    model_name: str = "mock-model"
    model: str = "mock-model"

    def __init__(
        self,
        stage: int = 1,
        domain_profile: str = "default",
        ctx: Any | None = None,
    ) -> None:
        self.stage = stage
        self.domain_profile = domain_profile
        self.ctx = ctx

    def invoke(self, messages: Any) -> _FakeInvokeResponse:
        """LangChain-compatible invoke — returns fixture JSON as response content."""
        return _FakeInvokeResponse(
            content=_get_fixture_json(self.stage, self.domain_profile, self.ctx)
        )

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResponse:
        """StructuredOutputProvider-compatible interface for the test and client path."""
        stage = request.stage if request.stage is not None else self.stage
        fixture_json = _get_fixture_json(stage, self.domain_profile, self.ctx)
        return StructuredGenerationResponse(
            raw_text=fixture_json,
            provider=self.provider_name,
            model=self.model_name,
            retry_count=0,
            trace_id=request.trace_id,
            metadata={
                "stage": stage,
                "domain_profile": self.domain_profile,
                "mock_fixture": current_mock_fixture(self.ctx),
                "supports_native_schema": self.supports_native_schema,
                "offline_mock": True,
            },
        )


@dataclass
class MockStructuredOutputProvider:
    """Legacy deterministic provider kept for backward compatibility."""

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
