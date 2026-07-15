# api/routers/interrupts.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["interrupts"])


@router.get(
    "/{session_id}/interrupt-records",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_interrupt_records(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    """List action_id ↔ interrupt_id mappings for the experimental interrupt adapter path."""
    try:
        return session_service.list_interrupt_records(
            session_id=session_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/interrupt-records/{interrupt_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_interrupt_record(
    session_id: str,
    interrupt_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Read one action_id ↔ interrupt_id mapping."""
    try:
        return session_service.get_interrupt_record(
            session_id=session_id,
            interrupt_id=interrupt_id,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
