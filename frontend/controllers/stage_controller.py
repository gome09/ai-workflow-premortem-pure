# frontend/controllers/stage_controller.py
from __future__ import annotations

import streamlit as st
from models.api_client import prepare_stage_operation
from models.session_state import refresh_actions


def execute_stage_operation(stage_id: int, stage_op: str, default_body: dict) -> None:
    result = prepare_stage_operation(
        st.session_state.session_id,
        int(stage_id),
        stage_op,
        default_body,
    )
    if result:
        st.success("阶段操作已记录；未运行 LLM / pytest / 接口 / 前端 / Docker。")
        st.session_state.stage_readiness = {}
        st.session_state.stage_resolution = {}
        refresh_actions()
        st.rerun()


def sync_missing_review_action(stage_id: int) -> None:
    result = prepare_stage_operation(
        st.session_state.session_id,
        int(stage_id),
        "sync-review-actions",
        {"reason": "frontend_sync_missing_action_binding"},
    )
    if result:
        st.success("已同步审核动作；请刷新后在人工动作队列处理。")
        st.session_state.stage_readiness = {}
        st.session_state.stage_resolution = {}
        refresh_actions()
        st.rerun()
