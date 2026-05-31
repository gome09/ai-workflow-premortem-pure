# api/routers/stage.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import (
    StageActionSyncRequest,
    StageAdvanceRequest,
    StageRerunRequest,
    StageRevisionRequest,
    StageRollbackRequest,
)
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


@router.get("/{session_id}/stage-readiness")
def list_stage_readiness(session_id: str) -> dict:
    """Read-only stage gate/readiness view for all four stages."""
    ctx = session_service.get_session(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return build_stage_readiness(ctx)


@router.get("/{session_id}/stage-readiness/{stage_id}")
def read_stage_readiness(session_id: str, stage_id: int) -> dict:
    """Read-only stage gate/readiness view for one stage."""
    ctx = session_service.get_session(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    try:
        return get_stage_readiness(ctx, stage_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{session_id}/stage-gate/{stage_id}")
def read_stage_gate(session_id: str, stage_id: int) -> dict:
    """Machine-readable StageGateResult for one stage.

    This is the authoritative advance/no-advance contract. It intentionally does
    not mutate session state or resolve any blocker.
    """
    ctx = session_service.get_session(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    try:
        return get_stage_gate_result(ctx, stage_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{session_id}/stage-resolution")
def list_stage_resolution_operations(session_id: str) -> dict:
    """Concrete next operations derived from the current StageBlockers."""
    ctx = session_service.get_session(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return build_stage_resolution_summary(ctx)


@router.get("/{session_id}/stage-resolution/{stage_id}")
def read_stage_resolution_operations(session_id: str, stage_id: int) -> dict:
    """Concrete next operations for one stage."""
    ctx = session_service.get_session(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    if stage_id < 1 or stage_id > 4:
        raise HTTPException(status_code=400, detail=f"stage must be 1..4, got {stage_id}")
    return {
        "stage_id": stage_id,
        "operations": [
            operation.model_dump(mode="json")
            for operation in build_stage_resolution_operations(ctx, stage_id)
        ],
    }


@router.get("/{session_id}/stages/{stage_id}/advancement-decision")
def read_stage_advancement_decision(session_id: str, stage_id: int) -> dict:
    """Unified StageAdvancementDecision for graph/API/frontend/report consumers.

    This endpoint is read-only: it evaluates gates and concrete operations but
    does not advance the workflow or run runtime validation.
    """
    try:
        return session_service.get_stage_advancement_decision(session_id, stage_id)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post("/{session_id}/stages/{stage_id}/advance")
def advance_stage_if_ready(session_id: str, stage_id: int, request: StageAdvanceRequest) -> dict:
    """Advance the stage only if the unified stage gate decision allows it.

    This endpoint does not run LLM/Search/pytest/API/Streamlit/Docker validation.
    It only mutates current_state when StageAdvancementDecision.can_advance is true.
    """
    try:
        return session_service.advance_stage_if_ready(
            session_id,
            stage_id=stage_id,
            reason=request.reason,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post("/{session_id}/stages/{stage_id}/rerun")
def prepare_stage_rerun(session_id: str, stage_id: int, request: StageRerunRequest) -> dict:
    """Prepare a stage for rerun without executing the LLM/runtime."""
    try:
        return session_service.prepare_stage_rerun(
            session_id,
            stage_id=stage_id,
            reason=request.reason,
            note=request.note,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post("/{session_id}/stages/{stage_id}/revise")
def request_stage_revision(session_id: str, stage_id: int, request: StageRevisionRequest) -> dict:
    """Prepare a stage for revision without executing the LLM/runtime."""
    try:
        return session_service.request_stage_revision(
            session_id,
            stage_id=stage_id,
            reason=request.reason,
            note=request.note,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post("/{session_id}/stages/{stage_id}/rollback")
def request_stage_rollback(session_id: str, stage_id: int, request: StageRollbackRequest) -> dict:
    """Rollback stage state without executing the LLM/runtime."""
    try:
        return session_service.request_stage_rollback(
            session_id,
            from_stage=stage_id,
            to_stage=request.to_stage,
            reason=request.reason,
            note=request.note,
            target_running=request.target_running,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)


@router.post("/{session_id}/stages/{stage_id}/sync-review-actions")
def sync_stage_review_actions(
    session_id: str, stage_id: int, request: StageActionSyncRequest
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
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Session not found" in message else 400
        raise HTTPException(status_code=status, detail=message)
