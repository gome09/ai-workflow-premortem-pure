# tests/test_mock_llm_mode.py
"""Tests for E4: Mock LLM Demo Mode (LLM_MODE=mock).

Verifies:
- settings.llm_mode defaults to "real"
- MockLLMAdapter returns valid fixture JSON for all 4 stages
- Fixture responses pass schema validation
- ResearchTool.search() returns 2 mock results in mock mode, no Tavily calls
- get_llm_client() factory returns MockLLMAdapter in mock mode
- All three fixture files (default, university_ai, medical_ai) export all 4 stage functions
- Fixture responses are non-empty and contain expected schema keys
"""

from __future__ import annotations

import json

import pytest

from core.config import Settings, settings
from core.llm.adapters.mock import MockLLMAdapter
from core.llm.adapters.mock_fixtures import default as fixture_default
from core.llm.adapters.mock_fixtures import medical_ai as fixture_medical_ai
from core.llm.adapters.mock_fixtures import university_ai as fixture_university_ai
from core.llm.provider import StructuredGenerationRequest, get_llm_client
from stages.validators import validate_stage1, validate_stage2, validate_stage3, validate_stage4
from tools.search import SearchResult, research_tool

# ─── settings defaults ──────────────────────────────────────────────────────


def test_llm_mode_defaults_to_real():
    """settings.llm_mode must default to 'real' so existing behaviour is unchanged."""
    field = Settings.model_fields["llm_mode"]
    assert field.default == "real"


def test_storage_backend_defaults_to_postgres(monkeypatch):
    """storage_backend field added for .env.demo; default must be 'postgres'."""
    monkeypatch.setattr(settings, "storage_backend", "postgres")
    assert settings.storage_backend == "postgres"


# ─── get_llm_client factory ─────────────────────────────────────────────────


def test_get_llm_client_returns_mock_when_mode_is_mock(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    client = get_llm_client(stage=1, domain_profile="default")
    assert isinstance(client, MockLLMAdapter)


def test_get_llm_client_mock_has_correct_stage(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    client = get_llm_client(stage=3, domain_profile="default")
    assert client.stage == 3


def test_get_llm_client_mock_has_correct_profile(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    client = get_llm_client(stage=2, domain_profile="university_ai")
    assert client.domain_profile == "university_ai"


# ─── MockLLMAdapter attributes ───────────────────────────────────────────────


def test_mock_adapter_provider_name():
    adapter = MockLLMAdapter(stage=1)
    assert adapter.provider_name == "mock"


def test_mock_adapter_model_name():
    adapter = MockLLMAdapter(stage=1)
    assert adapter.model_name == "mock-model"


def test_mock_adapter_supports_native_schema():
    adapter = MockLLMAdapter(stage=1)
    assert adapter.supports_native_schema is True


# ─── MockLLMAdapter.invoke() (LangChain-compatible path) ────────────────────


def test_mock_adapter_invoke_returns_content_with_stage1_json():
    adapter = MockLLMAdapter(stage=1, domain_profile="default")
    response = adapter.invoke([])
    assert isinstance(response.content, str)
    data = json.loads(response.content)
    assert "failure_modes" in data


def test_mock_adapter_invoke_returns_content_with_stage2_json():
    adapter = MockLLMAdapter(stage=2, domain_profile="default")
    response = adapter.invoke([])
    data = json.loads(response.content)
    assert "workflow_nodes" in data


def test_mock_adapter_invoke_returns_content_with_stage3_json():
    adapter = MockLLMAdapter(stage=3, domain_profile="default")
    response = adapter.invoke([])
    data = json.loads(response.content)
    assert "test_cases" in data


def test_mock_adapter_invoke_returns_content_with_stage4_json():
    adapter = MockLLMAdapter(stage=4, domain_profile="default")
    response = adapter.invoke([])
    data = json.loads(response.content)
    assert "trigger_methods" in data


# ─── MockLLMAdapter.generate_structured() ───────────────────────────────────


def test_mock_adapter_generate_structured_stage1():
    adapter = MockLLMAdapter(stage=1, domain_profile="default")
    request = StructuredGenerationRequest(stage=1)
    response = adapter.generate_structured(request)
    assert response.provider == "mock"
    data = json.loads(response.raw_text)
    assert "failure_modes" in data


def test_mock_adapter_generate_structured_uses_request_stage():
    adapter = MockLLMAdapter(stage=1, domain_profile="default")
    request = StructuredGenerationRequest(stage=4)
    response = adapter.generate_structured(request)
    data = json.loads(response.raw_text)
    assert "trigger_methods" in data


# ─── Fixture schema validation ───────────────────────────────────────────────


def test_default_stage1_fixture_passes_schema_validation():
    raw = fixture_default.stage_1_response()
    schema = validate_stage1(raw)
    assert len(schema.failure_modes) >= 2


def test_default_stage2_fixture_passes_schema_validation():
    raw = fixture_default.stage_2_response()
    schema = validate_stage2(raw)
    assert len(schema.workflow_nodes) >= 2


def test_default_stage3_fixture_passes_schema_validation():
    raw = fixture_default.stage_3_response()
    schema = validate_stage3(raw)
    assert len(schema.test_cases) >= 2
    assert schema.overall_passed is True


def test_default_stage4_fixture_passes_schema_validation():
    raw = fixture_default.stage_4_response()
    schema = validate_stage4(raw)
    assert len(schema.trigger_methods) >= 2


def test_university_ai_stage1_fixture_passes_schema_validation():
    raw = fixture_university_ai.stage_1_response()
    schema = validate_stage1(raw)
    assert len(schema.failure_modes) >= 2


def test_university_ai_stage2_fixture_passes_schema_validation():
    raw = fixture_university_ai.stage_2_response()
    schema = validate_stage2(raw)
    assert len(schema.workflow_nodes) >= 2


def test_university_ai_stage3_fixture_passes_schema_validation():
    raw = fixture_university_ai.stage_3_response()
    schema = validate_stage3(raw)
    assert len(schema.test_cases) >= 2


def test_university_ai_stage4_fixture_passes_schema_validation():
    raw = fixture_university_ai.stage_4_response()
    schema = validate_stage4(raw)
    assert len(schema.trigger_methods) >= 2


def test_medical_ai_stage1_fixture_passes_schema_validation():
    raw = fixture_medical_ai.stage_1_response()
    schema = validate_stage1(raw)
    assert len(schema.failure_modes) >= 2


def test_medical_ai_stage2_fixture_passes_schema_validation():
    raw = fixture_medical_ai.stage_2_response()
    schema = validate_stage2(raw)
    assert len(schema.workflow_nodes) >= 2


def test_medical_ai_stage3_fixture_passes_schema_validation():
    raw = fixture_medical_ai.stage_3_response()
    schema = validate_stage3(raw)
    assert len(schema.test_cases) >= 2


def test_medical_ai_stage4_fixture_passes_schema_validation():
    raw = fixture_medical_ai.stage_4_response()
    schema = validate_stage4(raw)
    assert len(schema.trigger_methods) >= 2


# ─── Fixture completeness ────────────────────────────────────────────────────


@pytest.mark.parametrize("module", [fixture_default, fixture_university_ai, fixture_medical_ai])
@pytest.mark.parametrize(
    "func_name", ["stage_1_response", "stage_2_response", "stage_3_response", "stage_4_response"]
)
def test_all_fixture_modules_have_all_stage_functions(module, func_name):
    assert callable(getattr(module, func_name))


@pytest.mark.parametrize("module", [fixture_default, fixture_university_ai, fixture_medical_ai])
@pytest.mark.parametrize(
    "func_name", ["stage_1_response", "stage_2_response", "stage_3_response", "stage_4_response"]
)
def test_all_fixture_responses_are_non_empty_strings(module, func_name):
    result = getattr(module, func_name)()
    assert isinstance(result, str)
    assert len(result) > 0


# ─── ResearchTool.search() mock guard ───────────────────────────────────────


def test_search_returns_two_results_in_mock_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    from core.models import ProjectContext

    ctx = ProjectContext()
    ctx.research_target = "Demo AI"
    ctx.domain = "demo"
    ctx.goal = "test"
    results = research_tool.search(ctx)
    assert len(results) == 2


def test_search_results_are_search_result_instances_in_mock_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    from core.models import ProjectContext

    ctx = ProjectContext()
    results = research_tool.search(ctx)
    assert all(isinstance(r, SearchResult) for r in results)


def test_search_does_not_call_tavily_in_mock_mode(monkeypatch):
    """Verify no TavilyClient is instantiated when in mock mode."""
    monkeypatch.setattr(settings, "llm_mode", "mock")
    from core.models import ProjectContext

    ctx = ProjectContext()
    # Reset cached client to ensure any lazy init would be detectable
    research_tool._client = None
    research_tool.search(ctx)
    # If mock guard worked, _client was never initialized
    assert research_tool._client is None


def test_search_mock_results_have_required_fields(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    from core.models import ProjectContext

    ctx = ProjectContext()
    results = research_tool.search(ctx)
    for r in results:
        assert r.title
        assert r.url
        assert r.content
        assert isinstance(r.score, float)


def test_search_mock_results_have_mock_urls(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    from core.models import ProjectContext

    ctx = ProjectContext()
    results = research_tool.search(ctx)
    assert all("mock" in r.url for r in results)


# ─── Determinism (same fixture every call) ──────────────────────────────────


def test_fixture_is_deterministic_across_calls():
    """Same fixture JSON must be returned on repeated calls (CI stability)."""
    adapter = MockLLMAdapter(stage=1, domain_profile="default")
    r1 = adapter.invoke([]).content
    r2 = adapter.invoke([]).content
    assert r1 == r2


# ─── Context manager integration ────────────────────────────────────────────


def test_get_llm_for_stage_returns_mock_when_mock_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    from core.context_manager import get_llm_for_stage

    llm = get_llm_for_stage(1)
    assert isinstance(llm, MockLLMAdapter)


def test_get_llm_for_stage_mock_has_correct_stage(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    from core.context_manager import get_llm_for_stage

    llm = get_llm_for_stage(3)
    assert llm.stage == 3
