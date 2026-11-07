# core/llm/errors.py
"""Unified classification and observability for external LLM call failures.

The project talks to OpenAI-compatible providers through several paths
(INIT, Stage 1-4 executors, eval ``llm_node`` and the LLM judge). Before this
module each path classified failures differently, logged raw provider text and
exposed an undifferentiated HTTP 500. This module keeps classification
deterministic and free of provider payloads:

- fixed error codes for metrics and API responses;
- retryability derived from the error code;
- logs and persisted messages never include ``str(exc)``.
"""

from __future__ import annotations

import logging
from typing import Literal

LLMErrorCode = Literal[
    "timeout",
    "rate_limit",
    "auth",
    "connection",
    "server_error",
    "bad_request",
    "provider_error",
]

RETRYABLE_ERROR_CODES: frozenset[str] = frozenset(
    {"timeout", "rate_limit", "connection", "server_error"}
)

_TIMEOUT_ERROR_TYPES = frozenset(
    {"TimeoutError", "APITimeoutError", "ReadTimeout", "ConnectTimeout"}
)
_AUTH_ERROR_TYPES = frozenset({"AuthenticationError", "PermissionDeniedError"})
_RATE_LIMIT_ERROR_TYPES = frozenset({"RateLimitError"})
_CONNECTION_ERROR_TYPES = frozenset(
    {"APIConnectionError", "ConnectError", "ConnectionError", "NetworkError"}
)
_SERVER_ERROR_TYPES = frozenset({"InternalServerError", "ServiceUnavailableError"})
_BAD_REQUEST_ERROR_TYPES = frozenset({"BadRequestError", "UnprocessableEntityError"})


class LLMCallError(RuntimeError):
    """Provider-neutral model call failure safe to surface to API clients.

    ``error_code`` is one of the fixed codes above; ``retryable`` tells callers
    whether a later retry may succeed. The exception message never contains
    provider payloads, prompts or credentials.
    """

    def __init__(
        self,
        *,
        error_code: LLMErrorCode,
        retryable: bool,
        error_type: str = "",
        stage: int | None = None,
        session_id: str = "",
        model: str = "",
        provider: str = "",
    ) -> None:
        self.error_code: LLMErrorCode = error_code
        self.retryable = retryable
        self.error_type = error_type
        self.stage = stage
        self.session_id = session_id
        self.model = model
        self.provider = provider
        super().__init__(f"LLM call failed: {error_code} ({error_type or 'unknown'})")


def _exception_type_name(exc: BaseException) -> str:
    return type(exc).__name__


def _status_code_of(exc: BaseException) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status
    return None


def classify_llm_error(exc: BaseException) -> tuple[LLMErrorCode, bool]:
    """Map an exception to a fixed error code and retryability.

    Classification intentionally uses exception class names and HTTP status
    codes instead of importing provider SDK classes, so it stays testable with
    plain fake exceptions and survives SDK upgrades.
    """
    name = _exception_type_name(exc)
    status_code = _status_code_of(exc)

    if name in _TIMEOUT_ERROR_TYPES or isinstance(exc, TimeoutError):
        code: LLMErrorCode = "timeout"
    elif name in _AUTH_ERROR_TYPES or status_code in {401, 403}:
        code = "auth"
    elif name in _RATE_LIMIT_ERROR_TYPES or status_code == 429:
        code = "rate_limit"
    elif name in _CONNECTION_ERROR_TYPES or isinstance(exc, ConnectionError):
        code = "connection"
    elif status_code is not None and status_code >= 500:
        code = "server_error"
    elif name in _SERVER_ERROR_TYPES:
        code = "server_error"
    elif name in _BAD_REQUEST_ERROR_TYPES or status_code in {400, 404, 409, 422}:
        code = "bad_request"
    else:
        code = "provider_error"
    return code, code in RETRYABLE_ERROR_CODES


def summarize_llm_error(exc: BaseException) -> str:
    """Return a log/persistence-safe summary; never includes ``str(exc)``."""
    code, _retryable = classify_llm_error(exc)
    return f"LLM {code} ({_exception_type_name(exc)})"


def build_llm_call_error(
    exc: BaseException,
    *,
    stage: int | None = None,
    session_id: str = "",
    model: str = "",
    provider: str = "",
) -> LLMCallError:
    code, retryable = classify_llm_error(exc)
    return LLMCallError(
        error_code=code,
        retryable=retryable,
        error_type=_exception_type_name(exc),
        stage=stage,
        session_id=session_id,
        model=model,
        provider=provider,
    )


def record_llm_failure(
    exc: BaseException,
    *,
    stage: int | None,
    session_id: str = "",
    model: str = "",
    provider: str = "",
    logger: logging.Logger,
    event: str = "llm_call_failed",
    extra_fields: dict[str, object] | None = None,
) -> tuple[LLMErrorCode, bool]:
    """Emit a structured warning and increment the failure metric.

    Logs contain only identifiers and the fixed error code. The metric call is
    best-effort and never blocks the caller's error path.
    """
    code, retryable = classify_llm_error(exc)
    payload: dict[str, object] = {
        "event": event,
        "stage": stage if stage is not None else "unknown",
        "session_id": session_id,
        "model": model,
        "provider": provider,
        "error_code": code,
        "error_type": _exception_type_name(exc),
        "retryable": retryable,
    }
    if extra_fields:
        payload.update(extra_fields)
    logger.warning(event, extra=payload)
    try:
        from api.metrics import record_llm_failure as _record_metric

        _record_metric(stage, code)
    except Exception:  # pragma: no cover - metrics must never break the error path
        logger.debug("record_llm_failure metric failed; non-fatal", exc_info=True)
    return code, retryable
