# api/routers/risk_treatments.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import RiskTreatmentReviewRequest, RiskTreatmentUpsertRequest
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.risk_treatment_service import (
    RiskTreatmentAuthorizationError,
    RiskTreatmentError,
    RiskTreatmentStaleError,
)
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["risk-treatments"])


def _http_error(exc: Exception) -> HTTPException:
    message = str(exc)
    if isinstance(exc, RiskTreatmentAuthorizationError):
        return HTTPException(status_code=403, detail=message)
    if isinstance(exc, RiskTreatmentStaleError):
        return HTTPException(status_code=409, detail=message)
    if isinstance(exc, RiskTreatmentError):
        return HTTPException(status_code=400, detail=message)
    if "Session not found" in message:
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)


@router.get(
    "/{session_id}/risk-treatments",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_risk_treatments(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.list_risk_treatments(session_id, tenant_id=ctx.tenant_id)
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc)


@router.post(
    "/{session_id}/risk-treatments",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def upsert_risk_treatment(
    session_id: str,
    body: RiskTreatmentUpsertRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.upsert_risk_treatment(
            session_id,
            source_type=body.source_type,
            source_id=body.source_id,
            owner=body.owner,
            mitigation_plan=body.mitigation_plan,
            status=body.status,
            note=body.note,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            tenant_id=ctx.tenant_id,
        )
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc)


@router.post(
    "/{session_id}/risk-treatments/{treatment_id}/review",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def review_risk_treatment(
    session_id: str,
    treatment_id: str,
    body: RiskTreatmentReviewRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.review_risk_treatment(
            session_id,
            treatment_id=treatment_id,
            decision=body.decision,
            note=body.note,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            tenant_id=ctx.tenant_id,
        )
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc)
