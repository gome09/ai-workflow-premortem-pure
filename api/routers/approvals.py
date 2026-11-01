# api/routers/approvals.py
"""Independent release approval — report generation is deliberately separate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import ReleaseApprovalRequest
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.approval_service import (
    ReleaseApprovalAuthorizationError,
    ReleaseApprovalNotApplicableError,
    ReleaseApprovalPrerequisiteError,
)
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["approvals"])


def _http_error(exc: Exception) -> HTTPException:
    message = str(exc)
    if isinstance(exc, ReleaseApprovalAuthorizationError):
        return HTTPException(status_code=403, detail=message)
    if isinstance(exc, ReleaseApprovalPrerequisiteError):
        return HTTPException(
            status_code=409,
            detail={
                "message": message,
                "blockers": [blocker.model_dump(mode="json") for blocker in exc.blockers],
            },
        )
    if isinstance(exc, ReleaseApprovalNotApplicableError):
        return HTTPException(status_code=400, detail=message)
    if "Session not found" in message:
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)


@router.get(
    "/{session_id}/approval-status",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_approval_status(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Release readiness plus report/evaluation/release status separation."""
    try:
        return session_service.get_approval_status(session_id, tenant_id=ctx.tenant_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.get(
    "/{session_id}/approvals",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_project_approvals(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_project_approvals(session_id, tenant_id=ctx.tenant_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.post(
    "/{session_id}/approvals/release",
    dependencies=[require_roles(Role.admin)],
)
def request_release_approval(
    session_id: str,
    body: ReleaseApprovalRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.request_release_approval(
            session_id,
            decision=body.decision,
            note=body.note,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            tenant_id=ctx.tenant_id,
        )
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc)
