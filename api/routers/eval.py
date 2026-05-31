# api/routers/eval.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import CalibrateEvalRunRequest, RunEvalCasesRequest, ScoreEvalCaseRequest
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["eval"])


@router.get("/{session_id}/eval-cases")
def list_eval_cases(session_id: str) -> list[dict]:
    try:
        return session_service.list_eval_cases(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-cases/{eval_id}/score")
def score_eval_case(session_id: str, eval_id: str, body: ScoreEvalCaseRequest) -> dict:
    try:
        return session_service.score_eval_case(
            session_id=session_id,
            eval_id=eval_id,
            human_score=body.human_score,
            human_comment=body.human_comment,
            passed=body.passed,
            actual_output=body.actual_output,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{session_id}/eval-runs")
def list_eval_runs(session_id: str, eval_id: str | None = None) -> list[dict]:
    try:
        return session_service.list_eval_runs(session_id=session_id, eval_id=eval_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-cases/run")
def run_eval_cases(session_id: str, body: RunEvalCasesRequest) -> dict:
    try:
        return session_service.run_eval_cases(
            session_id=session_id,
            eval_ids=body.eval_ids,
            run_mode=body.run_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/eval-cases/{eval_id}/run")
def run_single_eval_case(session_id: str, eval_id: str, body: RunEvalCasesRequest) -> dict:
    try:
        return session_service.run_eval_cases(
            session_id=session_id,
            eval_ids=[eval_id],
            run_mode=body.run_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{session_id}/eval-judgments")
def list_eval_judgments(
    session_id: str, eval_run_id: str | None = None, experiment_id: str | None = None
) -> list[dict]:
    try:
        return session_service.list_eval_judgments(
            session_id=session_id, eval_run_id=eval_run_id, experiment_id=experiment_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/human-calibrations")
def list_human_calibrations(
    session_id: str, eval_run_id: str | None = None, experiment_id: str | None = None
) -> list[dict]:
    try:
        return session_service.list_human_calibrations(
            session_id=session_id, eval_run_id=eval_run_id, experiment_id=experiment_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-runs/{run_id}/calibrate")
def calibrate_eval_run(session_id: str, run_id: str, body: CalibrateEvalRunRequest) -> dict:
    try:
        return session_service.calibrate_eval_run(
            session_id=session_id,
            run_id=run_id,
            human_label=body.human_label,
            human_comment=body.human_comment,
            reviewer_id=body.reviewer_id,
            disagreement_reason=body.disagreement_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
