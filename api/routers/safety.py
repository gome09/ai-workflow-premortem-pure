# api/routers/safety.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas import ResolveSafetyFindingRequest
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["safety"])


@router.get("/{session_id}/safety-findings")
def list_safety_findings(
    session_id: str,
    status: str | None = Query(default=None, description="open | resolved | dismissed"),
) -> list[dict]:
    try:
        return session_service.list_safety_findings(session_id=session_id, status=status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/safety-findings/{finding_id}/resolve")
def resolve_safety_finding(
    session_id: str,
    finding_id: str,
    body: ResolveSafetyFindingRequest,
) -> dict:
    try:
        return session_service.resolve_safety_finding(
            session_id=session_id,
            finding_id=finding_id,
            status=body.status,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
