# tests/test_observability_logs.py
"""Phase 2 observability: structured extras and log redaction guarantees."""

from __future__ import annotations

import json
import logging

from api.main import _JSONFormatter
from core import eval_runner
from core.approval_service import _log_approval_decided, _log_approval_denied
from core.llm.errors import record_llm_failure
from core.models import (
    EvalCase,
    ProjectApproval,
    ProjectContext,
    SessionState,
    Stage2Output,
    WorkflowNode,
)
from core.target_testing import TargetTestResponse

_SECRET = "sk-test-secret-999 and 110101199001011234"  # noqa: S105 - log-redaction fixture


def _record(**extras) -> logging.LogRecord:
    record = logging.LogRecord(
        name="core.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="event happened",
        args=(),
        exc_info=None,
    )
    for key, value in extras.items():
        setattr(record, key, value)
    return record


def test_json_formatter_preserves_extra_fields():
    record = _record(event="unit_event", session_id="session-1", error_code="timeout")

    payload = json.loads(_JSONFormatter().format(record))

    assert payload["event"] == "unit_event"
    assert payload["session_id"] == "session-1"
    assert payload["error_code"] == "timeout"
    assert payload["message"] == "event happened"
    assert payload["level"] == "INFO"


def test_json_formatter_serializes_non_json_values_safely():
    record = _record(event="unit_event", payload={"object": object()})

    text = _JSONFormatter().format(record)
    payload = json.loads(text)

    assert payload["event"] == "unit_event"
    assert payload["payload"]["object"].startswith("<object object at")


def test_llm_failure_log_and_formatter_exclude_secrets():
    exc = TimeoutError(_SECRET)
    logger = logging.getLogger("core.llm.errors")
    logger.propagate = True

    handler_records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            handler_records.append(record)

    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        record_llm_failure(exc, stage=1, session_id="session-1", logger=logger)
    finally:
        logger.removeHandler(handler)

    assert handler_records
    logging_record = handler_records[-1]
    assert "sk-test-secret" not in json.dumps(logging_record.__dict__, default=str)
    assert "110101199001011234" not in _JSONFormatter().format(logging_record)


def test_approval_decision_log_excludes_note_and_identity():
    ctx = ProjectContext()
    approval = ProjectApproval(
        session_id=ctx.session_id,
        status="approved",
        evaluation_version_digest="digest-1",
        decision_note=_SECRET,
        decided_by=_SECRET,
    )

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("core.approval_service")
    handler = _Capture(level=logging.INFO)
    logger.addHandler(handler)
    try:
        _log_approval_decided(ctx, approval, "admin", superseded_count=1)
        _log_approval_denied(ctx, "role_not_admin", "viewer")
    finally:
        logger.removeHandler(handler)

    rendered = "\n".join(_JSONFormatter().format(record) for record in records)
    assert "release_approval_decided" in rendered
    assert "release_approval_denied" in rendered
    assert "sk-test-secret" not in rendered
    assert "110101199001011234" not in rendered


def _ctx_with_eval_case() -> tuple[ProjectContext, EvalCase]:
    ctx = ProjectContext(
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.S3_RUNNING
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


def test_target_execution_log_does_not_include_response_body(monkeypatch, caplog):
    ctx, case = _ctx_with_eval_case()
    secret_body = "SECRET-TARGET-RESPONSE-BODY"  # noqa: S105 - redaction fixture

    class FakeAdapter:
        def __init__(self, config):
            self.config = config

        def execute(self, *args, **kwargs):
            return TargetTestResponse(
                outcome="success",
                output=secret_body,
                status_code=200,
                latency_ms=12,
                response_digest="digest",
            )

    monkeypatch.setattr(eval_runner, "HttpJsonTargetAdapter", FakeAdapter)
    monkeypatch.setattr(
        eval_runner,
        "sanitize_endpoint",
        lambda endpoint: "http://target.local/eval",
    )

    with caplog.at_level(logging.INFO, logger="core.eval_runner"):
        run = eval_runner.run_eval_case(
            ctx,
            eval_id=case.eval_id,
            run_mode="target_http",
            target_config=eval_runner.TargetSystemConfig(
                endpoint="http://target.local/eval", timeout_seconds=5.0
            ),
        )

    assert run.actual_output == secret_body
    assert any(record.message == "target_execution_finished" for record in caplog.records)
    for record in caplog.records:
        assert secret_body not in json.dumps(record.__dict__, default=str)
