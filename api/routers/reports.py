# api/routers/reports.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["reports"])


@router.post("/{session_id}/reports", dependencies=[require_roles(Role.editor, Role.admin)])
def create_report_artifact(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.create_report_artifact(
            session_id=session_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/reports", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)]
)
def list_report_artifacts(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_report_artifacts(session_id=session_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/reports/{report_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_report_artifact(
    session_id: str,
    report_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.get_report_artifact(
            session_id=session_id, report_id=report_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
