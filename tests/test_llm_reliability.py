# tests/test_llm_reliability.py
"""Phase 2 LLM reliability: timeout/retry config, error classification, 502 contract."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from auth.jwt import create_access_token
from core.config import Settings, settings
from core.context_manager import build_llm_kwargs_for_stage
from core.llm.errors import (
    LLMCallError,
    classify_llm_error,
    record_llm_failure,
    summarize_llm_error,
)
from core.llm.outbound_guard import OutboundPIIBlockedError
from core.models import ProjectContext, SessionState
from stages.base import BaseStageExecutor
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_SECRET_TEXT = "sk-live-secret-123 and 110101199001011234"  # noqa: S105 - log-redaction fixture


def _settings(**overrides):
    params = {
        "jwt_secret": "x" * 32,
        "llm_mode": "mock",
        "storage_backend": "sqlite",
        "demo_auto_auth": False,
        "deepseek_api_key": "",
        "tavily_api_key": "",
    }
    params.update(overrides)
    return Settings(_env_file=None, **params)


def test_llm_timeout_must_be_positive():
    with pytest.raises(ValidationError, match="LLM_TIMEOUT_SECONDS"):
        _settings(llm_timeout_seconds=0)


def test_llm_max_retries_must_be_non_negative():
    with pytest.raises(ValidationError, match="LLM_MAX_RETRIES"):
        _settings(llm_max_retries=-1)


def test_llm_kwargs_include_explicit_timeout_and_retries(monkeypatch):
    monkeypatch.setattr(settings, "llm_timeout_seconds", 45.0)
    monkeypatch.setattr(settings, "llm_max_retries", 2)

    kwargs = build_llm_kwargs_for_stage(2)

    assert kwargs["timeout"] == 45.0
    assert kwargs["max_retries"] == 2
    assert kwargs["model"] == settings.model_stage_2
    assert "extra_body" in kwargs


class APITimeoutError(TimeoutError):
    pass


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class InternalServerError(Exception):
    status_code = 503


class BadRequestError(Exception):
    status_code = 422


@pytest.mark.parametrize(
    ("exc", "expected_code", "expected_retryable"),
    [
        (APITimeoutError("slow"), "timeout", True),
        (RateLimitError("429"), "rate_limit", True),
        (AuthenticationError("401"), "auth", False),
        (APIConnectionError("refused"), "connection", True),
        (InternalServerError("upstream"), "server_error", True),
        (BadRequestError("bad"), "bad_request", False),
        (RuntimeError("weird"), "provider_error", False),
    ],
)
def test_classify_llm_error(exc, expected_code, expected_retryable):
    code, retryable = classify_llm_error(exc)

    assert code == expected_code
    assert retryable is expected_retryable


def test_summarize_llm_error_never_includes_exception_text():
    exc = APITimeoutError(f"provider leaked {_SECRET_TEXT}")

    summary = summarize_llm_error(exc)

    assert summary == "LLM timeout (APITimeoutError)"
    assert "sk-live-secret" not in summary
    assert "110101199001011234" not in summary


class _FailingLLM:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def invoke(self, messages):
        raise self._exc


class _TestExecutor(BaseStageExecutor):
    stage_id = 1

    def build_system_prompt(self, ctx: ProjectContext) -> str:
        return "stage test system prompt"

    def parse_output(self, raw_text: str, ctx: ProjectContext) -> ProjectContext:
        return ctx


def test_stage_executor_maps_provider_failure_to_llm_call_error(monkeypatch, caplog):
    ctx = ProjectContext(
        research_target="Internal assistant",
        domain="Internal FAQ",
        goal="Answer questions",
    )
    ctx.current_state = SessionState.S1_RUNNING
    llm = _FailingLLM(TimeoutError(_SECRET_TEXT))
    monkeypatch.setattr("stages.base.get_llm_for_stage_with_context", lambda stage, ctx: llm)

    with caplog.at_level(logging.WARNING, logger="stages.base"):
        with pytest.raises(LLMCallError) as exc_info:
            _TestExecutor().run(ctx, "continue")

    error = exc_info.value
    assert error.error_code == "timeout"
    assert error.retryable is True
    assert error.stage == 1
    assert error.session_id == ctx.session_id

    trace = ctx.llm_traces[-1]
    assert trace.error_message == "LLM timeout (TimeoutError)"
    assert trace.metadata["error_code"] == "timeout"

    rendered_logs = [str(record.__dict__) for record in caplog.records]
    assert all("sk-live-secret" not in item for item in rendered_logs)
    assert all("110101199001011234" not in item for item in rendered_logs)


def test_outbound_pii_blocked_error_is_not_wrapped(monkeypatch):
    ctx = ProjectContext()
    llm = _FailingLLM(OutboundPIIBlockedError("non-text sensitive content"))
    monkeypatch.setattr("stages.base.get_llm_for_stage_with_context", lambda stage, ctx: llm)

    with pytest.raises(OutboundPIIBlockedError):
        _TestExecutor().run(ctx, "continue")


def test_structured_output_failure_returns_parser_status_without_crashing():
    executor = _TestExecutor()
    ctx = ProjectContext()

    result = executor.parse_structured_output("not json at all", ctx)

    assert result.parser_status in {"non_json", "validation_failed"}
    assert result.validation_errors


def test_record_llm_failure_logs_fixed_code_only(caplog):
    exc = AuthenticationError(f"bad key {_SECRET_TEXT}")

    with caplog.at_level(logging.WARNING, logger="core.llm.errors"):
        code, retryable = record_llm_failure(
            exc,
            stage=3,
            session_id="session-1",
            logger=logging.getLogger("core.llm.errors"),
        )

    assert code == "auth"
    assert retryable is False
    record = caplog.records[-1]
    assert "sk-live-secret" not in str(record.__dict__)
    assert "110101199001011234" not in str(record.__dict__)


def _headers() -> dict:
    token = create_access_token({"sub": "test-user", "tenant_id": "test-tenant", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


def test_chat_returns_structured_502_on_model_timeout(monkeypatch, tmp_path):
    cache = MemoryCache(ttl_seconds=3600)
    from unittest.mock import patch

    monkeypatch.setattr(settings, "workflow_execution_mode", "single_step")
    backend = SQLiteSessionStore(db_path=str(tmp_path / "chat_502.db"))
    backend.initialize()
    ctx = ProjectContext(
        tenant_id="test-tenant",
        research_target="Internal assistant",
        domain="Internal FAQ",
        goal="Answer questions",
    )
    ctx.current_state = SessionState.S1_RUNNING
    backend.save(ctx)

    llm = _FailingLLM(TimeoutError(_SECRET_TEXT))
    monkeypatch.setattr("stages.base.get_llm_for_stage_with_context", lambda stage, ctx: llm)

    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", backend),
        patch("core.session_service.context_cache", cache),
    ):
        from api.main import app

        client = TestClient(app)
        response = client.post(
            f"/chat/{ctx.session_id}",
            json={"user_input": "continue"},
            headers=_headers(),
        )

    assert response.status_code == 502
    body = response.json()
    assert body["error_code"] == "timeout"
    assert body["retryable"] is True
    assert body["session_id"] == ctx.session_id
    assert body["stage"] == 1
    assert "sk-live-secret" not in response.text
    assert "110101199001011234" not in response.text
