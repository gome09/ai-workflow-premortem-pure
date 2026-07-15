# api/routers/eval.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import CalibrateEvalRunRequest, RunEvalCasesRequest, ScoreEvalCaseRequest
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["eval"])


@router.get(
    "/{session_id}/eval-cases", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)]
)
def list_eval_cases(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_eval_cases(session_id=session_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/eval-cases/{eval_id}/score",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def score_eval_case(
    session_id: str,
    eval_id: str,
    body: ScoreEvalCaseRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.score_eval_case(
            session_id=session_id,
            eval_id=eval_id,
            human_score=body.human_score,
            human_comment=body.human_comment,
            passed=body.passed,
            actual_output=body.actual_output,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{session_id}/eval-runs", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)]
)
def list_eval_runs(
    session_id: str,
    eval_id: str | None = None,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_eval_runs(
            session_id=session_id, eval_id=eval_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-cases/run", dependencies=[require_roles(Role.editor, Role.admin)])
def run_eval_cases(
    session_id: str,
    body: RunEvalCasesRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.run_eval_cases(
            session_id=session_id,
            eval_ids=body.eval_ids,
            run_mode=body.run_mode,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{session_id}/eval-cases/{eval_id}/run", dependencies=[require_roles(Role.editor, Role.admin)]
)
def run_single_eval_case(
    session_id: str,
    eval_id: str,
    body: RunEvalCasesRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.run_eval_cases(
            session_id=session_id,
            eval_ids=[eval_id],
            run_mode=body.run_mode,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{session_id}/eval-judgments",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_eval_judgments(
    session_id: str,
    eval_run_id: str | None = None,
    experiment_id: str | None = None,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_eval_judgments(
            session_id=session_id,
            eval_run_id=eval_run_id,
            experiment_id=experiment_id,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/human-calibrations",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_human_calibrations(
    session_id: str,
    eval_run_id: str | None = None,
    experiment_id: str | None = None,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_human_calibrations(
            session_id=session_id,
            eval_run_id=eval_run_id,
            experiment_id=experiment_id,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/eval-runs/{run_id}/calibrate",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def calibrate_eval_run(
    session_id: str,
    run_id: str,
    body: CalibrateEvalRunRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.calibrate_eval_run(
            session_id=session_id,
            run_id=run_id,
            human_label=body.human_label,
            human_comment=body.human_comment,
            reviewer_id=body.reviewer_id,
            disagreement_reason=body.disagreement_reason,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
