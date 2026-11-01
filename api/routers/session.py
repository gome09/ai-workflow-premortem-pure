# api/routers/session.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas import (
    AddMaterialsRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteSessionResponse,
    ExportReportResponse,
    MaterialsAddedResponse,
    RecoverWorkflowRequest,
    RecoverWorkflowResponse,
    RenameSessionRequest,
    RenameSessionResponse,
    ResolveFlagRequest,
    ResolveFlagResponse,
    RiskFactorScoresRequest,
    RiskOverrideRequest,
    RiskProfileResponse,
    ScenarioSummaryResponse,
    SessionListItem,
    SessionOverviewResponse,
    UpdateDataClassificationRequest,
    UpdateDataClassificationResponse,
)
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.models import ProjectContext
from core.risk.assessment import RiskOverridePermissionError
from core.session_service import DataClassificationDowngradeError, session_service
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
        created_by=ctx.user_id,
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
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[SessionListItem]:
    """列出当前 tenant 的最近会话。"""
    return [
        SessionListItem(**item)
        for item in session_service.list_sessions(
            limit=limit, tenant_id=ctx.tenant_id, offset=offset
        )
    ]


@router.get(
    "/{session_id}",
    response_model=ProjectContext,
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_session(session_id: str, ctx: TenantContext = Depends(get_current_tenant)) -> dict:
    """获取完整会话上下文。"""
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return project_ctx.model_dump(mode="json")


@router.get(
    "/{session_id}/overview",
    response_model=SessionOverviewResponse,
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_session_overview(
    session_id: str, ctx: TenantContext = Depends(get_current_tenant)
) -> SessionOverviewResponse:
    """获取会话首屏概览（不含 stage 输出与明细轨迹）。"""
    overview = session_service.get_session_overview(session_id, tenant_id=ctx.tenant_id)
    if not overview:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return SessionOverviewResponse(**overview)


@router.patch(
    "/{session_id}/name",
    response_model=RenameSessionResponse,
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def rename_session(
    session_id: str,
    body: RenameSessionRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """修改当前 tenant 下的会话名称。"""
    try:
        return session_service.rename_session(
            session_id,
            body.name,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch(
    "/{session_id}/data-classification",
    response_model=UpdateDataClassificationResponse,
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def update_data_classification(
    session_id: str,
    body: UpdateDataClassificationRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> UpdateDataClassificationResponse:
    """覆写会话数据分级。

    协议层只做角色准入与异常映射；分级顺序、降级门槛、审计与持久化
    统一由 SessionService.update_data_classification 承担。
    """
    try:
        result = session_service.update_data_classification(
            session_id,
            data_classification=body.data_classification,
            note=body.note,
            actor_role=ctx.role,
            tenant_id=ctx.tenant_id,
        )
    except DataClassificationDowngradeError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return UpdateDataClassificationResponse(**result)


@router.get(
    "/{session_id}/risk-profile",
    response_model=RiskProfileResponse,
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
)
def get_risk_profile(
    session_id: str, ctx: TenantContext = Depends(get_current_tenant)
) -> RiskProfileResponse:
    """读取会话的六因子风险画像、生效等级与 override 历史。"""
    try:
        return RiskProfileResponse(
            **session_service.get_risk_profile(session_id, tenant_id=ctx.tenant_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/{session_id}/risk-profile",
    response_model=RiskProfileResponse,
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def set_risk_profile(
    session_id: str,
    body: RiskFactorScoresRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> RiskProfileResponse:
    """显式设置六因子风险输入（写入 risk_profile_updated 审计事件）。"""
    try:
        return RiskProfileResponse(
            **session_service.set_risk_profile(
                session_id,
                impact=body.impact,
                autonomy=body.autonomy,
                data_sensitivity=body.data_sensitivity,
                reversibility=body.reversibility,
                scale=body.scale,
                external_exposure=body.external_exposure,
                rationale=body.rationale,
                actor=ctx.user_id or "user",
                actor_role=ctx.role,
                tenant_id=ctx.tenant_id,
            )
        )
    except RiskOverridePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{session_id}/risk-profile/override",
    response_model=RiskProfileResponse,
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def override_risk_tier(
    session_id: str,
    body: RiskOverrideRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> RiskProfileResponse:
    """人工覆写风险等级；降级需 admin 且不得低于确定性 floor。"""
    try:
        return RiskProfileResponse(
            **session_service.override_risk_tier(
                session_id,
                requested_tier=body.requested_tier,
                reason=body.reason,
                actor=ctx.user_id or "user",
                actor_role=ctx.role,
                tenant_id=ctx.tenant_id,
            )
        )
    except RiskOverridePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{session_id}",
    response_model=DeleteSessionResponse,
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


@router.post(
    "/{session_id}/workflow/recover",
    response_model=RecoverWorkflowResponse,
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def recover_workflow(
    session_id: str,
    body: RecoverWorkflowRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """将 ERROR / RECOVERY_REQUIRED 会话显式恢复到可推进状态。

    仅协议适配：状态合法性、目标状态白名单与审计由
    `core.workflow_state_service.recover_workflow` 承担。
    """
    try:
        return session_service.recover_workflow(
            session_id,
            target_state=body.target_state,
            note=body.note,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        detail = str(e)
        if detail.startswith("Session not found"):
            raise HTTPException(status_code=404, detail=detail)
        if "is not blocked" in detail:
            raise HTTPException(status_code=409, detail=detail)
        # 未知/不可恢复的 target_state 属于请求参数错误。
        raise HTTPException(status_code=400, detail=detail)


@router.post(
    "/{session_id}/materials",
    response_model=MaterialsAddedResponse,
    dependencies=[require_roles(Role.editor, Role.admin)],
)
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


@router.post(
    "/{session_id}/flags/resolve",
    response_model=ResolveFlagResponse,
    dependencies=[require_roles(Role.editor, Role.admin)],
)
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
    "/{session_id}/export",
    response_model=ExportReportResponse,
    dependencies=[require_roles(Role.viewer, Role.editor, Role.admin)],
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
