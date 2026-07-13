# api/routers/chat.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api.limiter import limiter
from api.schemas import SendMessageRequest, SendMessageResponse
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from core.session_service import session_service
from core.stage_advancement_coordinator import build_stage_advancement_decision
from core.stage_resolution_service import (
    build_stage_resolution_summary,
    get_next_required_operation,
)
from core.stage_scope_service import current_stage_id

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/{session_id}", dependencies=[require_roles(Role.editor, Role.admin)])
@limiter.limit("30/hour")
def send_message(
    request: Request,
    session_id: str,
    body: SendMessageRequest,
    ctx: TenantContext = Depends(get_current_tenant),
):
    try:
        ai_reply, project_ctx = session_service.send_message(
            session_id=session_id,
            user_input=body.user_input,
            user_materials=body.user_materials,
            tenant_id=ctx.tenant_id,
        )
        stage_id = current_stage_id(project_ctx)
        stage_decision = build_stage_advancement_decision(
            project_ctx,
            stage_id,
            decision_source="chat_message_processed",
            reason="chat_message_processed",
            append_trace=False,
        )
        return SendMessageResponse(
            session_id=session_id,
            ai_reply=ai_reply,
            current_state=project_ctx.current_state.value,
            pending_flags_count=len(project_ctx.get_pending_flags()),
            pending_actions_count=len(project_ctx.get_pending_actions()),
            stage_advancement_decision=stage_decision.model_dump(mode="json"),
            next_required_operation=get_next_required_operation(project_ctx, stage_id),
            stage_resolution_summary=build_stage_resolution_summary(project_ctx),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
