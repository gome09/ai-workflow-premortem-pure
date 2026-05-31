# api/routers/eval_datasets.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import (
    CreateEvalDatasetFromStage3Request,
    CreateEvalDatasetRequest,
    SetEvalDatasetBaselineRequest,
    UpdateEvalDatasetCasesRequest,
)
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["eval-datasets"])


@router.get("/{session_id}/eval-datasets")
def list_eval_datasets(session_id: str) -> list[dict]:
    try:
        return session_service.list_eval_datasets(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-datasets")
def create_eval_dataset(session_id: str, body: CreateEvalDatasetRequest) -> dict:
    try:
        return session_service.create_eval_dataset(
            session_id,
            name=body.name,
            description=body.description,
            case_ids=body.case_ids,
            scenario_type=body.scenario_type,
            source=body.source,
            version=body.version,
            tags=body.tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/eval-datasets/from-stage3")
def create_eval_dataset_from_stage3(
    session_id: str, body: CreateEvalDatasetFromStage3Request
) -> dict:
    try:
        return session_service.create_eval_dataset_from_stage3(
            session_id,
            name=body.name,
            description=body.description,
            version=body.version,
            owner=body.owner,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{session_id}/eval-datasets/{dataset_id}")
def get_eval_dataset(session_id: str, dataset_id: str) -> dict:
    try:
        return session_service.get_eval_dataset(session_id, dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-datasets/{dataset_id}/cases")
def add_eval_dataset_cases(
    session_id: str, dataset_id: str, body: UpdateEvalDatasetCasesRequest
) -> dict:
    try:
        return session_service.add_eval_cases_to_dataset(
            session_id, dataset_id=dataset_id, eval_ids=body.eval_ids
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{session_id}/eval-datasets/{dataset_id}/cases")
def remove_eval_dataset_cases(
    session_id: str, dataset_id: str, body: UpdateEvalDatasetCasesRequest
) -> dict:
    try:
        return session_service.remove_eval_cases_from_dataset(
            session_id, dataset_id=dataset_id, eval_ids=body.eval_ids
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/eval-datasets/{dataset_id}/baseline")
def set_eval_dataset_baseline(
    session_id: str, dataset_id: str, body: SetEvalDatasetBaselineRequest
) -> dict:
    try:
        return session_service.set_eval_dataset_baseline(
            session_id,
            dataset_id=dataset_id,
            baseline_experiment_id=body.baseline_experiment_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
