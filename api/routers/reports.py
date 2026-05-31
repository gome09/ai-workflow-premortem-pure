# api/routers/reports.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["reports"])


@router.post("/{session_id}/reports")
def create_report_artifact(session_id: str) -> dict:
    try:
        return session_service.create_report_artifact(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/reports")
def list_report_artifacts(session_id: str) -> list[dict]:
    try:
        return session_service.list_report_artifacts(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/reports/{report_id}")
def get_report_artifact(session_id: str, report_id: str) -> dict:
    try:
        return session_service.get_report_artifact(session_id=session_id, report_id=report_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
