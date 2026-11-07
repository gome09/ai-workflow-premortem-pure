# api/routers/release_gate.py
"""Read-only machine gate for external deployment pipelines.

Only a tenant-scoped service token can call this endpoint. A release is
allowed only when the response is HTTP 200 with ``decision == "allow"``.
Every other status or decision must block deployment.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from api.limiter import limiter
from auth.service_tokens import ServiceTokenContext, get_service_token_context
from core.release_gate_service import (
    ReleaseGateDecision,
    ReleaseGateNotFoundError,
    ReleaseGateUnavailableError,
)
from core.session_service import session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/release-gate", tags=["release-gate"])


def _record_metric(decision: str, reason_code: str) -> None:
    try:
        from api.metrics import record_release_gate_check

        record_release_gate_check(decision, reason_code)
    except Exception:  # pragma: no cover - metrics must never change the gate decision
        logger.debug("record_release_gate_check failed; non-fatal", exc_info=True)


def _unavailable_response(session_id: str) -> JSONResponse:
    decision = ReleaseGateDecision(
        decision="block",
        reason_code="gate_unavailable",
        reason_detail="Release gate is unavailable; deployment must be blocked.",
        approval_status="unknown",
        applicable=False,
        session_id=session_id,
        checked_at=datetime.now(UTC),
    )
    return JSONResponse(
        status_code=503,
        content=decision.model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{session_id}", response_model=ReleaseGateDecision)
@limiter.limit("60/minute")
def check_release_gate(
    request: Request,
    session_id: str,
    response: Response,
    token: ServiceTokenContext = Depends(get_service_token_context),
) -> ReleaseGateDecision | JSONResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        payload = session_service.get_release_gate_decision(
            session_id,
            token_id=token.token_id,
            tenant_id=token.tenant_id,
        )
    except ReleaseGateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except ReleaseGateUnavailableError:
        _record_metric("block", "gate_unavailable")
        return _unavailable_response(session_id)
    except Exception as exc:  # noqa: BLE001 - the gate must fail closed
        logger.error(
            "release_gate_evaluation_failed",
            extra={
                "event": "release_gate_evaluation_failed",
                "tenant_id": token.tenant_id,
                "token_id": token.token_id,
                "session_id": session_id,
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        _record_metric("block", "gate_unavailable")
        return _unavailable_response(session_id)

    decision = ReleaseGateDecision.model_validate(payload)
    _record_metric(decision.decision, decision.reason_code)
    return decision
