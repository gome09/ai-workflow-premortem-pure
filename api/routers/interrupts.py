# api/routers/interrupts.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["interrupts"])


@router.get("/{session_id}/interrupt-records")
def list_interrupt_records(session_id: str) -> list[dict]:
    """List action_id ↔ interrupt_id mappings for the v0.6 adapter path."""
    try:
        return session_service.list_interrupt_records(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/interrupt-records/{interrupt_id}")
def get_interrupt_record(session_id: str, interrupt_id: str) -> dict:
    """Read one action_id ↔ interrupt_id mapping."""
    try:
        return session_service.get_interrupt_record(
            session_id=session_id,
            interrupt_id=interrupt_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
