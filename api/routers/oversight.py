# api/routers/oversight.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas import ResolveActionRequest
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["oversight"])


@router.get(
    "/{session_id}/actions", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)]
)
def list_actions(
    session_id: str,
    status: str | None = Query(
        default=None, description="pending | resolved | cancelled | superseded | stale"
    ),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    """列出当前会话的人工监督动作。"""
    try:
        return session_service.list_actions(
            session_id=session_id, status=status, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/actions/{action_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_action(
    session_id: str,
    action_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """读取单个人工监督动作。"""
    try:
        return session_service.get_action(
            session_id=session_id, action_id=action_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/actions/{action_id}/resolution-logs",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_action_resolution_logs(
    session_id: str,
    action_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    """列出某个人工动作的处理尝试记录。"""
    try:
        return session_service.list_action_resolution_logs(
            session_id=session_id,
            action_id=action_id,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/actions/{action_id}/resolve",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def resolve_action(
    session_id: str,
    action_id: str,
    body: ResolveActionRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """处理人工监督动作，并返回显式 v0.7 结果合同。"""
    try:
        result = session_service.resolve_action_with_result(
            session_id=session_id,
            action_id=action_id,
            decision=body.decision,
            note=body.note,
            payload_after=body.payload_after,
            idempotency_key=body.idempotency_key,
            expected_before_hash=body.expected_before_hash,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    status = result.get("result_status")
    if status in {"resolved", "idempotent_replay"}:
        return result
    if status in {"stale", "conflict", "not_pending"}:
        raise HTTPException(status_code=409, detail=result)
    if status == "validation_failed":
        raise HTTPException(status_code=422, detail=result)
    if status == "not_found":
        raise HTTPException(status_code=404, detail=result)
    raise HTTPException(status_code=400, detail=result)


@router.get(
    "/{session_id}/audit-events", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)]
)
def list_audit_events(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    """列出当前会话的审计事件。"""
    try:
        return session_service.list_audit_events(session_id=session_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
