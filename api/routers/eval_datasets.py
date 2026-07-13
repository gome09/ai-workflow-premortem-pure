# api/routers/eval_datasets.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import (
    CreateEvalDatasetFromStage3Request,
    CreateEvalDatasetRequest,
    SetEvalDatasetBaselineRequest,
    UpdateEvalDatasetCasesRequest,
)
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["eval-datasets"])


@router.get(
    "/{session_id}/eval-datasets",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_eval_datasets(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_eval_datasets(session_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/eval-datasets", dependencies=[require_roles(Role.editor, Role.admin)])
def create_eval_dataset(
    session_id: str,
    body: CreateEvalDatasetRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
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
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{session_id}/eval-datasets/from-stage3", dependencies=[require_roles(Role.editor, Role.admin)]
)
def create_eval_dataset_from_stage3(
    session_id: str,
    body: CreateEvalDatasetFromStage3Request,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.create_eval_dataset_from_stage3(
            session_id,
            name=body.name,
            description=body.description,
            version=body.version,
            owner=body.owner,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{session_id}/eval-datasets/{dataset_id}",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_eval_dataset(
    session_id: str,
    dataset_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.get_eval_dataset(session_id, dataset_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/eval-datasets/{dataset_id}/cases",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def add_eval_dataset_cases(
    session_id: str,
    dataset_id: str,
    body: UpdateEvalDatasetCasesRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.add_eval_cases_to_dataset(
            session_id, dataset_id=dataset_id, eval_ids=body.eval_ids, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{session_id}/eval-datasets/{dataset_id}/cases", dependencies=[require_roles(Role.admin)]
)
def remove_eval_dataset_cases(
    session_id: str,
    dataset_id: str,
    body: UpdateEvalDatasetCasesRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.remove_eval_cases_from_dataset(
            session_id, dataset_id=dataset_id, eval_ids=body.eval_ids, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{session_id}/eval-datasets/{dataset_id}/baseline",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def set_eval_dataset_baseline(
    session_id: str,
    dataset_id: str,
    body: SetEvalDatasetBaselineRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.set_eval_dataset_baseline(
            session_id,
            dataset_id=dataset_id,
            baseline_experiment_id=body.baseline_experiment_id,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
