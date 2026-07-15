# api/routers/traces.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas import TraceToEvalCaseRequest, TraceToEvalDatasetRequest
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["traces"])


@router.get(
    "/{session_id}/traces", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)]
)
def list_traces(
    session_id: str,
    stage: int | None = Query(default=None),
    trace_type: str | None = Query(default=None),
    parser_status: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    """List traces captured during stage execution."""
    try:
        return session_service.list_traces(
            session_id,
            stage=stage,
            trace_type=trace_type,
            parser_status=parser_status,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/traces/{trace_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_trace(
    session_id: str,
    trace_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Read a single LLM trace."""
    try:
        return session_service.get_trace(session_id, trace_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/traces/{trace_id}/to-eval-case",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def trace_to_eval_case(
    session_id: str,
    trace_id: str,
    body: TraceToEvalCaseRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.trace_to_eval_case(
            session_id=session_id,
            trace_id=trace_id,
            expected_behavior=body.expected_behavior,
            target_node_id=body.target_node_id,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{session_id}/traces/to-eval-dataset", dependencies=[require_roles(Role.editor, Role.admin)]
)
def traces_to_eval_dataset(
    session_id: str,
    body: TraceToEvalDatasetRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.traces_to_eval_dataset(
            session_id=session_id,
            trace_ids=body.trace_ids,
            name=body.name,
            description=body.description,
            version=body.version,
            owner=body.owner,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
