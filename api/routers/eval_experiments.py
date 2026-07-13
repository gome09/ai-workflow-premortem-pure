# api/routers/eval_experiments.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import (
    CompareEvalExperimentRequest,
    CreateEvalExperimentRequest,
    RunEvalExperimentRequest,
)
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["eval-experiments"])


@router.get(
    "/{session_id}/eval-experiments",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_eval_experiments(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_eval_experiments(session_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/eval-experiments", dependencies=[require_roles(Role.editor, Role.admin)]
)
def create_eval_experiment(
    session_id: str,
    body: CreateEvalExperimentRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
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
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{session_id}/eval-experiments/{experiment_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_eval_experiment(
    session_id: str,
    experiment_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.get_eval_experiment(
            session_id, experiment_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/eval-experiments/{experiment_id}/run",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def run_eval_experiment(
    session_id: str,
    experiment_id: str,
    body: RunEvalExperimentRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.run_eval_experiment(
            session_id,
            experiment_id=experiment_id,
            dry_run_only=body.dry_run_only,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{session_id}/eval-experiments/{experiment_id}/metrics",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_eval_experiment_metrics(
    session_id: str,
    experiment_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.get_eval_experiment_metrics(
            session_id, experiment_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/eval-experiments/{experiment_id}/comparison",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_eval_experiment_comparison(
    session_id: str,
    experiment_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        experiment = session_service.get_eval_experiment(
            session_id, experiment_id, tenant_id=ctx.tenant_id
        )
        return experiment.get("comparison_summary") or {}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/eval-experiments/{experiment_id}/comparison",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def compare_eval_experiment(
    session_id: str,
    experiment_id: str,
    body: CompareEvalExperimentRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.compare_eval_experiment(
            session_id,
            experiment_id=experiment_id,
            baseline_experiment_id=body.baseline_experiment_id,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
