# api/routers/traces.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas import TraceToEvalCaseRequest, TraceToEvalDatasetRequest
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["traces"])


@router.get("/{session_id}/traces")
def list_traces(
    session_id: str,
    stage: int | None = Query(default=None),
    trace_type: str | None = Query(default=None),
    parser_status: str | None = Query(default=None),
) -> list[dict]:
    """List traces captured during stage execution."""
    try:
        return session_service.list_traces(
            session_id,
            stage=stage,
            trace_type=trace_type,
            parser_status=parser_status,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/traces/{trace_id}")
def get_trace(session_id: str, trace_id: str) -> dict:
    """Read a single LLM trace."""
    try:
        return session_service.get_trace(session_id, trace_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/traces/{trace_id}/to-eval-case")
def trace_to_eval_case(session_id: str, trace_id: str, body: TraceToEvalCaseRequest) -> dict:
    try:
        return session_service.trace_to_eval_case(
            session_id=session_id,
            trace_id=trace_id,
            expected_behavior=body.expected_behavior,
            target_node_id=body.target_node_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/traces/to-eval-dataset")
def traces_to_eval_dataset(session_id: str, body: TraceToEvalDatasetRequest) -> dict:
    try:
        return session_service.traces_to_eval_dataset(
            session_id=session_id,
            trace_ids=body.trace_ids,
            name=body.name,
            description=body.description,
            version=body.version,
            owner=body.owner,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
