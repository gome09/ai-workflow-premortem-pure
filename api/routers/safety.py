# api/routers/safety.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas import ResolveSafetyFindingRequest
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["safety"])


@router.get(
    "/{session_id}/safety-findings",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_safety_findings(
    session_id: str,
    status: str | None = Query(default=None, description="open | resolved | dismissed"),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_safety_findings(
            session_id=session_id, status=status, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/safety-findings/{finding_id}/resolve",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def resolve_safety_finding(
    session_id: str,
    finding_id: str,
    body: ResolveSafetyFindingRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.resolve_safety_finding(
            session_id=session_id,
            finding_id=finding_id,
            status=body.status,
            note=body.note,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
