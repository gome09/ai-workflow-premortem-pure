# api/routers/redteam.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import (
    CreateRedTeamCaseRequest,
    CreateRedTeamDatasetRequest,
    GenerateRedTeamCasesRequest,
    ResolveRedTeamCaseRequest,
)
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["redteam"])


@router.get("/{session_id}/redteam/cases")
def list_redteam_cases(session_id: str) -> list[dict]:
    try:
        return session_service.list_redteam_cases(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/redteam/coverage")
def redteam_coverage_summary(session_id: str) -> dict:
    try:
        return session_service.redteam_coverage_summary(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/redteam/generate")
def generate_redteam_cases(session_id: str, body: GenerateRedTeamCasesRequest) -> dict:
    try:
        return session_service.generate_redteam_cases(session_id, stage=body.stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/redteam/cases")
def create_redteam_case(session_id: str, body: CreateRedTeamCaseRequest) -> dict:
    try:
        return session_service.create_redteam_case(session_id, **body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/redteam/cases/{case_id}/approve")
def approve_redteam_case(session_id: str, case_id: str, body: ResolveRedTeamCaseRequest) -> dict:
    try:
        return session_service.approve_redteam_case(session_id, case_id, note=body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/redteam/cases/{case_id}/reject")
def reject_redteam_case(session_id: str, case_id: str, body: ResolveRedTeamCaseRequest) -> dict:
    try:
        return session_service.reject_redteam_case(session_id, case_id, note=body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/redteam/cases/{case_id}/to-eval-case")
def redteam_case_to_eval_case(session_id: str, case_id: str) -> dict:
    try:
        return session_service.redteam_case_to_eval_case(session_id, case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/redteam/datasets")
def create_redteam_dataset(session_id: str, body: CreateRedTeamDatasetRequest) -> dict:
    try:
        return session_service.create_redteam_dataset(
            session_id,
            name=body.name,
            description=body.description,
            case_ids=body.case_ids,
            version=body.version,
            owner=body.owner,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
