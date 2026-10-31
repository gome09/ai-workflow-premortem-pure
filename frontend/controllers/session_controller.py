# frontend/controllers/session_controller.py
from __future__ import annotations

import streamlit as st
from models.api_client import (
    add_materials_to_session,
    api_delete,
    bootstrap_scenario_input,
    create_session,
    get_session,
    get_stage_readiness,
    invalidate_api_cache,
    invalidate_session_cache,
    list_interrupt_records,
    rename_session,
    send_message,
)
from models.api_client import (
    recover_workflow as recover_workflow_api,
)
from models.session_state import (
    _activate_created_session,
    _append_bootstrap_exchange,
    refresh_actions,
    refresh_flags,
    restore_messages_from_ctx,
)


def load_builtin_scenario(
    selected_scenario_id: str | None,
    scenario_detail: dict | None,
    selected_scenario_label: str | None,
) -> None:
    """下拉选择本身就是「加载场景」动作：创建绑定场景的会话并自动发送样例输入。"""
    if not (
        selected_scenario_id
        and scenario_detail
        and selected_scenario_label != st.session_state.loaded_scenario_label
    ):
        return
    with st.spinner("正在加载内置场景..."):
        created = create_session(selected_scenario_id)
        if created:
            _activate_created_session(created)
            scenario_input = scenario_detail.get("input_sample", "")
            result = (
                bootstrap_scenario_input(created["session_id"], scenario_input)
                if scenario_input
                else None
            )
            if result:
                _append_bootstrap_exchange(scenario_input, result)
                refresh_flags()
                refresh_actions()
            st.session_state.loaded_scenario_label = selected_scenario_label
    if created:
        st.rerun()


def create_blank_session() -> None:
    with st.spinner("创建中..."):
        created = create_session()
    if created:
        _activate_created_session(created)
        st.session_state.reset_scenario_selector = True
        st.rerun()


def select_session(session: dict) -> None:
    if session["session_id"] == st.session_state.session_id:
        return
    st.session_state.session_id = session["session_id"]
    st.session_state.current_state = session["current_state"]
    # 切换会话必须丢弃上一会话的派生门禁状态。
    st.session_state.stage_resolution = {}
    st.session_state.stage_advancement_decisions = {}
    st.session_state.stage_advancement_decision = None

    ctx = get_session(session["session_id"])
    if ctx:
        st.session_state.selected_scenario_id = ctx.get("selected_scenario_id")
        st.session_state.messages = restore_messages_from_ctx(ctx)
        st.session_state.pending_flags = [
            f for f in ctx.get("flagged_items", []) if f["status"] == "pending"
        ]
        st.session_state.pending_actions = [
            a for a in ctx.get("pending_actions", []) if a["status"] == "pending"
        ]
        st.session_state.interrupt_records = list_interrupt_records(session["session_id"])
        st.session_state.stage_readiness = get_stage_readiness(session["session_id"])
    st.rerun()


def rename_session_event(session_id: str, name: str) -> None:
    renamed = rename_session(session_id, name)
    if renamed:
        st.toast(f"会话已重命名为：{renamed['session_name']}")
        st.rerun()


def delete_session(session_id: str) -> dict | None:
    result = api_delete(f"/sessions/{session_id}")
    if result is not None:
        invalidate_api_cache("sessions:")
        invalidate_session_cache(session_id)
    return result


def refresh_current_session() -> None:
    """手动刷新：清空前端读取缓存，并重新拉取当前会话的派生状态。"""
    invalidate_api_cache()
    if st.session_state.session_id:
        refresh_flags()
        refresh_actions()
    st.rerun()


def add_materials(materials: list[str]) -> bool:
    with st.spinner("上传中..."):
        ok = add_materials_to_session(st.session_state.session_id, materials)
    if ok:
        st.success(f"✅ 已添加 {len(materials)} 份资料。")
    else:
        st.error("上传失败，请重试。")
    return ok


def recover_workflow(target_state: str, note: str = "") -> None:
    """从阻断态显式恢复到可推进状态，并同步前端状态。"""
    with st.spinner("正在恢复工作流..."):
        result = recover_workflow_api(
            st.session_state.session_id,
            target_state,
            note,
        )
    if result:
        st.session_state.current_state = result["after"]
        st.toast(f"工作流已恢复到：{result['after']}")
        refresh_flags()
        refresh_actions()
        st.rerun()


def handle_send(user_input: str, materials: list[str] | None = None) -> None:
    """
    统一处理发送消息的逻辑：
    追加用户消息 → 调用 API → 追加 AI 回复 → 刷新状态
    """
    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_input,
            "metadata": {},
        }
    )

    with st.spinner("🤖 AI 思考中，请稍候..."):
        result = send_message(
            session_id=st.session_state.session_id,
            user_input=user_input,
            materials=materials,
        )

    if result:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result["ai_reply"],
                "metadata": {},
            }
        )
        st.session_state.current_state = result["current_state"]
        refresh_flags()
        refresh_actions()
