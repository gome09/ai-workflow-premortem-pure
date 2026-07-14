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
    UpdateDataClassificationRequest,
)
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.audit_service import append_audit_event
from core.session_service import session_service
from scenarios import get_scenario, list_scenarios
from storage.cache import context_cache
from storage.session_store import session_store

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


@router.patch(
    "/{session_id}/data-classification",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def update_data_classification(
    session_id: str,
    body: UpdateDataClassificationRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """覆写会话数据分级。

    规则：升级或同级修改允许 editor+；降级必须 admin，且写 AuditEvent。
    """
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    before = project_ctx.data_classification
    after = body.data_classification
    order = {"public_demo": 0, "business_internal": 1, "sensitive_personal": 2}
    is_downgrade = order[after] < order[before]

    if is_downgrade:
        # 降级必须 admin
        if Role(ctx.role) != Role.admin:
            raise HTTPException(
                status_code=403,
                detail="Downgrading data_classification requires admin role",
            )

    append_audit_event(
        project_ctx,
        actor="user",
        event_type="data_classification_changed",
        target_type="session",
        target_id=session_id,
        before={"data_classification": before},
        after={"data_classification": after},
        metadata={
            "note": body.note,
            "is_downgrade": is_downgrade,
            "actor_role": ctx.role,
        },
    )
    project_ctx.data_classification = after
    session_store.save(project_ctx)
    context_cache.set(project_ctx)
    return {
        "ok": True,
        "session_id": session_id,
        "before": before,
        "after": after,
        "is_downgrade": is_downgrade,
    }


@router.delete(
    "/{session_id}",
    dependencies=[require_roles(Role.admin)],
)
def delete_session(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Admin 删除会话（审计事件归档保留，写 session_purged 处置事件）。"""
    try:
        return session_service.delete_session(
            session_id, purged_by=ctx.user_id or ctx.role, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
