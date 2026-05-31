# api/routers/session.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    AddMaterialsRequest,
    CreateSessionResponse,
    ResolveFlagRequest,
    SessionListItem,
)
from core.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/", response_model=CreateSessionResponse)
def create_session() -> CreateSessionResponse:
    """创建新会话。"""
    ctx = session_service.create_session()
    return CreateSessionResponse(
        session_id=ctx.session_id,
        current_state=ctx.current_state.value,
    )


@router.get("/", response_model=list[SessionListItem])
def list_sessions(limit: int = Query(default=20, ge=1, le=100)) -> list[SessionListItem]:
    """列出最近会话。"""
    return [SessionListItem(**item) for item in session_service.list_sessions(limit=limit)]


@router.get("/{session_id}")
def get_session(session_id: str) -> dict:
    """获取完整会话上下文。"""
    ctx = session_service.get_session(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return ctx.model_dump(mode="json")


@router.post("/{session_id}/materials")
def add_materials(session_id: str, body: AddMaterialsRequest) -> dict:
    """向会话追加人工补充资料。"""
    try:
        return session_service.add_materials(session_id, body.materials)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/flags/resolve")
def resolve_flag(session_id: str, body: ResolveFlagRequest) -> dict:
    """处理【需核验】项。action 取值为 verified 或 dismissed。"""
    if body.action not in {"verified", "dismissed"}:
        raise HTTPException(
            status_code=400,
            detail="action must be either 'verified' or 'dismissed'",
        )

    try:
        return session_service.resolve_flag(
            session_id=session_id,
            flag_id=body.flag_id,
            action=body.action,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/export")
def export_report(
    session_id: str, format: str = Query(default="json", description="json | markdown")
) -> dict:
    """导出完整分析报告。"""
    try:
        return session_service.export_report(session_id, format=format)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
