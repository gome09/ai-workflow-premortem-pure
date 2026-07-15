# api/routers/stage.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.limiter import limiter
from api.schemas import (
    StageActionSyncRequest,
    StageAdvanceRequest,
    StageRerunRequest,
    StageRevisionRequest,
    StageRollbackRequest,
)
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service
from core.stage_readiness_service import (
    build_stage_readiness,
    get_stage_gate_result,
    get_stage_readiness,
)
from core.stage_resolution_service import (
    build_stage_resolution_operations,
    build_stage_resolution_summary,
)

router = APIRouter(prefix="/sessions", tags=["stage-readiness"])


@router.get(
    "/{session_id}/stage-readiness",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_stage_readiness(session_id: str, ctx: TenantContext = Depends(get_current_tenant)) -> dict:
    """Read-only stage gate/readiness view for all four stages."""
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return build_stage_readiness(project_ctx)


@router.get(
    "/{session_id}/stage-readiness/{stage_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def read_stage_readiness(
    session_id: str, stage_id: int, ctx: TenantContext = Depends(get_current_tenant)
) -> dict:
    """Read-only stage gate/readiness view for one stage."""
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    try:
        return get_stage_readiness(project_ctx, stage_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/{session_id}/stage-gate/{stage_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def read_stage_gate(
    session_id: str, stage_id: int, ctx: TenantContext = Depends(get_current_tenant)
) -> dict:
    """Machine-readable StageGateResult for one stage.

    This is the authoritative advance/no-advance contract. It intentionally does
    not mutate session state or resolve any blocker.
    """
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    try:
        return get_stage_gate_result(project_ctx, stage_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/{session_id}/stage-resolution",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_stage_resolution_operations(
    session_id: str, ctx: TenantContext = Depends(get_current_tenant)
) -> dict:
    """Concrete next operations derived from the current StageBlockers."""
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return build_stage_resolution_summary(project_ctx)


@router.get(
    "/{session_id}/stage-resolution/{stage_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def read_stage_resolution_operations(
    session_id: str, stage_id: int, ctx: TenantContext = Depends(get_current_tenant)
) -> dict:
    """Concrete next operations for one stage."""
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    if stage_id < 1 or stage_id > 4:
        raise HTTPException(status_code=400, detail=f"stage must be 1..4, got {stage_id}")
    return {
        "stage_id": stage_id,
        "operations": [
            operation.model_dump(mode="json")
            for operation in build_stage_resolution_operations(project_ctx, stage_id)
        ],
    }


@router.get(
    "/{session_id}/stages/{stage_id}/advancement-decision",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def read_stage_advancement_decision(
    session_id: str, stage_id: int, ctx: TenantContext = Depends(get_current_tenant)
) -> dict:
    """Unified StageAdvancementDecision for graph/API/frontend/report consumers.

    This endpoint is read-only: it evaluates gates and concrete operations but
    does not advance the workflow or run runtime validation.
    """
    try:
        return session_service.get_stage_advancement_decision(
            session_id, stage_id, tenant_id=ctx.tenant_id
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post(
    "/{session_id}/stages/{stage_id}/advance", dependencies=[require_roles(Role.editor, Role.admin)]
)
@limiter.limit("20/hour")
def advance_stage_if_ready(
    request: Request,
    session_id: str,
    stage_id: int,
    body: StageAdvanceRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Advance the stage only if the unified stage gate decision allows it.

    This endpoint does not run LLM/Search/pytest/API/Streamlit/Docker validation.
    It only mutates current_state when StageAdvancementDecision.can_advance is true.
    """
    try:
        return session_service.advance_stage_if_ready(
            session_id,
            stage_id=stage_id,
            reason=body.reason,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post(
    "/{session_id}/stages/{stage_id}/rerun", dependencies=[require_roles(Role.editor, Role.admin)]
)
def prepare_stage_rerun(
    session_id: str,
    stage_id: int,
    request: StageRerunRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Prepare a stage for rerun without executing the LLM/runtime."""
    try:
        return session_service.prepare_stage_rerun(
            session_id,
            stage_id=stage_id,
            reason=request.reason,
            note=request.note,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post(
    "/{session_id}/stages/{stage_id}/revise", dependencies=[require_roles(Role.editor, Role.admin)]
)
def request_stage_revision(
    session_id: str,
    stage_id: int,
    request: StageRevisionRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Prepare a stage for revision without executing the LLM/runtime."""
    try:
        return session_service.request_stage_revision(
            session_id,
            stage_id=stage_id,
            reason=request.reason,
            note=request.note,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post(
    "/{session_id}/stages/{stage_id}/rollback",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def request_stage_rollback(
    session_id: str,
    stage_id: int,
    request: StageRollbackRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Rollback stage state without executing the LLM/runtime."""
    try:
        return session_service.request_stage_rollback(
            session_id,
            from_stage=stage_id,
            to_stage=request.to_stage,
            reason=request.reason,
            note=request.note,
            target_running=request.target_running,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post(
    "/{session_id}/stages/{stage_id}/sync-review-actions",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def sync_stage_review_actions(
    session_id: str,
    stage_id: int,
    request: StageActionSyncRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Regenerate missing review actions for visible stage blockers.

    Readiness/resolution GET endpoints remain read-only; this explicit endpoint
    is the mutating repair action.
    """
    try:
        return session_service.sync_stage_review_actions(
            session_id,
            stage_id=stage_id,
            reason=request.reason,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.get(
    "/{session_id}/gate-report",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_gate_report(
    session_id: str,
    stage: int = Query(..., ge=1, le=4),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Return a detailed per-rule gate decision report for one stage.

    Surfaces each gate rule's individual pass / block / skip result so that
    users and evaluators can understand exactly why a stage advance was blocked,
    without reading source code.
    """
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    from core.gates.engine import evaluate_stage_gate

    try:
        result = evaluate_stage_gate(project_ctx, stage, detailed=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    report = result.__dict__.get("report")
    if report is None:
        raise HTTPException(status_code=500, detail="Gate report could not be generated.")

    return report.model_dump(mode="json")
