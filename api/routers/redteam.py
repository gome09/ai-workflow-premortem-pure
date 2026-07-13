# api/routers/redteam.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import (
    CreateRedTeamCaseRequest,
    CreateRedTeamDatasetRequest,
    GenerateRedTeamCasesRequest,
    ResolveRedTeamCaseRequest,
)
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["redteam"])


@router.get(
    "/{session_id}/redteam/cases",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_redteam_cases(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict]:
    try:
        return session_service.list_redteam_cases(session_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/redteam/coverage",
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def redteam_coverage_summary(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.redteam_coverage_summary(session_id, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/redteam/generate", dependencies=[require_roles(Role.editor, Role.admin)]
)
def generate_redteam_cases(
    session_id: str,
    body: GenerateRedTeamCasesRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.generate_redteam_cases(
            session_id, stage=body.stage, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/redteam/cases", dependencies=[require_roles(Role.editor, Role.admin)])
def create_redteam_case(
    session_id: str,
    body: CreateRedTeamCaseRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.create_redteam_case(
            session_id, **body.model_dump(), tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{session_id}/redteam/cases/{case_id}/approve",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def approve_redteam_case(
    session_id: str,
    case_id: str,
    body: ResolveRedTeamCaseRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.approve_redteam_case(
            session_id, case_id, note=body.note, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{session_id}/redteam/cases/{case_id}/reject",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def reject_redteam_case(
    session_id: str,
    case_id: str,
    body: ResolveRedTeamCaseRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.reject_redteam_case(
            session_id, case_id, note=body.note, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{session_id}/redteam/cases/{case_id}/to-eval-case",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def redteam_case_to_eval_case(
    session_id: str,
    case_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.redteam_case_to_eval_case(
            session_id, case_id, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{session_id}/redteam/datasets", dependencies=[require_roles(Role.editor, Role.admin)]
)
def create_redteam_dataset(
    session_id: str,
    body: CreateRedTeamDatasetRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    try:
        return session_service.create_redteam_dataset(
            session_id,
            name=body.name,
            description=body.description,
            case_ids=body.case_ids,
            version=body.version,
            owner=body.owner,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
