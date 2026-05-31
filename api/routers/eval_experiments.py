# api/routers/eval_experiments.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import (
    CompareEvalExperimentRequest,
    CreateEvalExperimentRequest,
    RunEvalExperimentRequest,
)
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["eval-experiments"])


@router.get("/{session_id}/eval-experiments")
def list_eval_experiments(session_id: str) -> list[dict]:
    try:
        return session_service.list_eval_experiments(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-experiments")
def create_eval_experiment(session_id: str, body: CreateEvalExperimentRequest) -> dict:
    try:
        return session_service.create_eval_experiment(
            session_id,
            dataset_id=body.dataset_id,
            name=body.name,
            description=body.description,
            run_mode=body.run_mode,
            provider=body.provider,
            model=body.model,
            baseline_experiment_id=body.baseline_experiment_id,
            run_config=body.run_config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{session_id}/eval-experiments/{experiment_id}")
def get_eval_experiment(session_id: str, experiment_id: str) -> dict:
    try:
        return session_service.get_eval_experiment(session_id, experiment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-experiments/{experiment_id}/run")
def run_eval_experiment(
    session_id: str, experiment_id: str, body: RunEvalExperimentRequest
) -> dict:
    try:
        return session_service.run_eval_experiment(
            session_id,
            experiment_id=experiment_id,
            dry_run_only=body.dry_run_only,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{session_id}/eval-experiments/{experiment_id}/metrics")
def get_eval_experiment_metrics(session_id: str, experiment_id: str) -> dict:
    try:
        return session_service.get_eval_experiment_metrics(session_id, experiment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/eval-experiments/{experiment_id}/comparison")
def get_eval_experiment_comparison(session_id: str, experiment_id: str) -> dict:
    try:
        experiment = session_service.get_eval_experiment(session_id, experiment_id)
        return experiment.get("comparison_summary") or {}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-experiments/{experiment_id}/comparison")
def compare_eval_experiment(
    session_id: str, experiment_id: str, body: CompareEvalExperimentRequest
) -> dict:
    try:
        return session_service.compare_eval_experiment(
            session_id,
            experiment_id=experiment_id,
            baseline_experiment_id=body.baseline_experiment_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
