# tests/test_target_http_adapter.py
"""Real target HTTP adapter and target_http eval run semantics."""

from __future__ import annotations

import json

import httpx
import pytest

from core import eval_runner
from core.eval_runner import run_eval_case
from core.models import (
    EvalCase,
    ProjectContext,
    SessionState,
    Stage2Output,
    WorkflowNode,
)
from core.risk.models import RiskFactorScores
from core.target_testing import HttpJsonTargetAdapter, TargetSystemConfig, TargetTestResponse


def _config(endpoint: str = "http://target.local/eval") -> TargetSystemConfig:
    return TargetSystemConfig(endpoint=endpoint, timeout_seconds=5.0)


def test_success_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": "target answer"})

    adapter = HttpJsonTargetAdapter(
        _config(), transport=httpx.MockTransport(handler), allowed_hosts="target.local"
    )
    result = adapter.execute("input")

    assert result.outcome == "success"
    assert result.output == "target answer"
    assert result.status_code == 200
    assert result.latency_ms is not None


def test_http_error_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream exploded")

    adapter = HttpJsonTargetAdapter(
        _config(), transport=httpx.MockTransport(handler), allowed_hosts="target.local"
    )
    result = adapter.execute("input")

    assert result.outcome == "failed"
    assert result.status_code == 500
    assert result.error_code == "http_500"
    assert "upstream exploded" in result.error_message


def test_timeout_response():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    adapter = HttpJsonTargetAdapter(
        _config(), transport=httpx.MockTransport(handler), allowed_hosts="target.local"
    )
    result = adapter.execute("input")

    assert result.outcome == "timeout"
    assert result.error_code == "target_timeout"


def test_abnormal_response_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    adapter = HttpJsonTargetAdapter(
        _config(), transport=httpx.MockTransport(handler), allowed_hosts="target.local"
    )
    result = adapter.execute("input")

    assert result.outcome == "error"
    assert result.error_code == "response_contract_error"


def test_missing_output_field_is_contract_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"other": "value"})

    adapter = HttpJsonTargetAdapter(
        _config(), transport=httpx.MockTransport(handler), allowed_hosts="target.local"
    )
    result = adapter.execute("input")

    assert result.outcome == "error"
    assert result.error_code == "response_contract_error"


def test_endpoint_not_allowlisted_is_refused_without_request():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"output": "should not happen"})

    adapter = HttpJsonTargetAdapter(
        _config(), transport=httpx.MockTransport(handler), allowed_hosts="other.local"
    )
    result = adapter.execute("input")

    assert result.outcome == "error"
    assert result.error_code == "endpoint_not_allowed"
    assert calls == []


def test_sensitive_personal_payload_is_masked_before_target():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen.append(body["input"])
        return httpx.Response(200, json={"output": "ok"})

    adapter = HttpJsonTargetAdapter(
        _config(), transport=httpx.MockTransport(handler), allowed_hosts="target.local"
    )
    adapter.execute("id 110101199001011234", classification="sensitive_personal")

    assert seen
    assert "110101199001011234" not in seen[0]


def _ctx_with_eval_case() -> tuple[ProjectContext, EvalCase]:
    ctx = ProjectContext(
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.S3_RUNNING
    ctx.risk_profile = RiskFactorScores(
        impact=0, autonomy=0, data_sensitivity=1, reversibility=0, scale=0, external_exposure=0
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-1",
                stage_name="Answer",
                model_assigned="model",
                human_action="review",
                check_criteria="citations",
                failure_modes_addressed=[],
                prompt_template="answer",
            )
        ]
    )
    case = EvalCase(
        session_id=ctx.session_id,
        stage_id=3,
        target_node_id="N-1",
        scenario_type="normal",
        input_payload="policy question",
        expected_behavior="answer",
        pass_criteria=["citation"],
        passed=True,
    )
    ctx.eval_cases.append(case)
    return ctx, case


@pytest.mark.parametrize(
    ("response", "expected_outcome", "expected_status"),
    [
        (TargetTestResponse(outcome="success", output="answer", status_code=200), "success", "completed"),
        (
            TargetTestResponse(
                outcome="failed",
                status_code=500,
                error_code="http_500",
                error_message="boom",
            ),
            "failed",
            "completed",
        ),
        (TargetTestResponse(outcome="timeout", error_code="target_timeout"), "timeout", "failed"),
        (TargetTestResponse(outcome="error", error_code="response_contract_error"), "error", "failed"),
    ],
)
def test_run_eval_case_records_target_outcome(
    monkeypatch, response, expected_outcome, expected_status
):
    ctx, case = _ctx_with_eval_case()

    class FakeAdapter:
        def __init__(self, config):
            self.config = config

        def execute(self, *args, **kwargs):
            return response.model_copy(deep=True)

    monkeypatch.setattr(eval_runner, "HttpJsonTargetAdapter", FakeAdapter)

    run = run_eval_case(
        ctx,
        eval_id=case.eval_id,
        run_mode="target_http",
        target_config=_config(),
    )

    assert run.execution_kind == "real_target_execution"
    assert run.execution_outcome == expected_outcome
    assert run.status == expected_status
    assert run.evaluation_version_digest
    assert run.target_endpoint == "http://target.local/eval"


def test_simulation_modes_are_not_real_target_execution(monkeypatch):
    ctx, case = _ctx_with_eval_case()

    manual_run = run_eval_case(ctx, eval_id=case.eval_id, run_mode="manual")
    dry_run = run_eval_case(ctx, eval_id=case.eval_id, run_mode="dry_run")

    assert manual_run.execution_kind == "manual_simulation"
    assert dry_run.execution_kind == "dry_run_simulation"
    assert manual_run.execution_kind != "real_target_execution"
    assert dry_run.execution_kind != "real_target_execution"


def test_target_http_requires_config():
    ctx, case = _ctx_with_eval_case()
    with pytest.raises(ValueError, match="target_config is required"):
        run_eval_case(ctx, eval_id=case.eval_id, run_mode="target_http")
