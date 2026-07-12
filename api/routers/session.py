# api/routers/session.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas import (
    AddMaterialsRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    ResolveFlagRequest,
    ScenarioSummaryResponse,
    SessionListItem,
)
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service
from scenarios import get_scenario, list_scenarios

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post(
    "/", response_model=CreateSessionResponse, dependencies=[require_roles(Role.editor, Role.admin)]
)
def create_session(
    body: CreateSessionRequest | None = None,
    ctx: TenantContext = Depends(get_current_tenant),
) -> CreateSessionResponse:
    """创建新会话。"""
    project_ctx = session_service.create_session(
        tenant_id=ctx.tenant_id,
        scenario_id=body.scenario_id if body else None,
    )
    return CreateSessionResponse(
        session_id=project_ctx.session_id,
        current_state=project_ctx.current_state.value,
        selected_scenario_id=project_ctx.selected_scenario_id,
    )


@router.get(
    "/scenarios",
    response_model=list[ScenarioSummaryResponse],
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_builtin_scenarios() -> list[ScenarioSummaryResponse]:
    return [ScenarioSummaryResponse(**item.to_api_dict()) for item in list_scenarios()]


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioSummaryResponse,
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_builtin_scenario(scenario_id: str) -> ScenarioSummaryResponse:
    try:
        scenario = get_scenario(scenario_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ScenarioSummaryResponse(**scenario.to_api_dict(include_input_sample=True))


@router.get(
    "/",
    response_model=list[SessionListItem],
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[SessionListItem]:
    """列出当前 tenant 的最近会话。"""
    return [
        SessionListItem(**item)
        for item in session_service.list_sessions(limit=limit, tenant_id=ctx.tenant_id)
    ]


@router.get("/{session_id}", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)])
def get_session(session_id: str, ctx: TenantContext = Depends(get_current_tenant)) -> dict:
    """获取完整会话上下文。"""
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return project_ctx.model_dump(mode="json")


@router.post("/{session_id}/materials", dependencies=[require_roles(Role.editor, Role.admin)])
def add_materials(
    session_id: str,
    body: AddMaterialsRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """向会话追加人工补充资料。"""
    try:
        return session_service.add_materials(session_id, body.materials, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/flags/resolve", dependencies=[require_roles(Role.editor, Role.admin)])
def resolve_flag(
    session_id: str,
    body: ResolveFlagRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """处理【需核验】项。"""
    if body.action not in {"verified", "dismissed"}:
        raise HTTPException(
            status_code=400, detail="action must be either 'verified' or 'dismissed'"
        )
    try:
        return session_service.resolve_flag(
            session_id=session_id,
            flag_id=body.flag_id,
            action=body.action,
            note=body.note,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{session_id}/export", dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)]
)
def export_report(
    session_id: str,
    format: str = Query(default="json", description="json | markdown"),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """导出完整分析报告。"""
    try:
        return session_service.export_report(session_id, format=format, tenant_id=ctx.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
