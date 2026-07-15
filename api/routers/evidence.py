# api/routers/evidence.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import VerifyEvidenceRequest
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["evidence"])


@router.get(
    "/{session_id}/evidence", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)]
)
def list_evidence(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_evidence(session_id=session_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/evidence/{evidence_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_evidence(
    session_id: str,
    evidence_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.get_evidence(
            session_id=session_id, evidence_id=evidence_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/evidence/{evidence_id}/verify",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def verify_evidence(
    session_id: str,
    evidence_id: str,
    body: VerifyEvidenceRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.verify_evidence(
            session_id=session_id,
            evidence_id=evidence_id,
            note=body.note,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
