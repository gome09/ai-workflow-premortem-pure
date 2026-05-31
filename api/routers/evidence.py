# api/routers/evidence.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import VerifyEvidenceRequest
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["evidence"])


@router.get("/{session_id}/evidence")
def list_evidence(session_id: str) -> list[dict]:
    try:
        return session_service.list_evidence(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/evidence/{evidence_id}")
def get_evidence(session_id: str, evidence_id: str) -> dict:
    try:
        return session_service.get_evidence(session_id=session_id, evidence_id=evidence_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/evidence/{evidence_id}/verify")
def verify_evidence(session_id: str, evidence_id: str, body: VerifyEvidenceRequest) -> dict:
    try:
        return session_service.verify_evidence(
            session_id=session_id,
            evidence_id=evidence_id,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
