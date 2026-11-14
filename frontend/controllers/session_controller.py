# frontend/controllers/session_controller.py
from __future__ import annotations

import streamlit as st
from models.api_client import (
    add_materials_to_session,
    api_delete,
    bootstrap_scenario_input,
    create_session,
    get_session_checked,
    get_stage_readiness_checked,
    invalidate_api_cache,
    invalidate_session_cache,
    list_actions_checked,
    list_interrupt_records_checked,
    rename_session,
    send_message,
)
from models.api_client import (
    recover_workflow as recover_workflow_api,
)
from models.feedback import ApiError, clear_flash, describe_api_error, set_flash, show_api_error
from models.session_state import (
    _activate_created_session,
    _append_bootstrap_exchange,
    refresh_actions,
    refresh_flags,
    restore_messages_from_ctx,
)

_UNKNOWN_OUTCOME_KINDS = {"timeout", "connection", "unknown", "invalid_response"}


def _outcome_is_unknown(exc: ApiError) -> bool:
    """超时/断连/5xx 无法断言服务端未处理，必须与明确拒绝区分。"""
    if exc.kind in _UNKNOWN_OUTCOME_KINDS:
        return True
    return exc.kind == "http" and exc.status_code >= 500


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
    created: dict | None = None
    try:
        with st.spinner("正在加载内置场景..."):
            created = create_session(selected_scenario_id)
            _activate_created_session(created)
            scenario_input = scenario_detail.get("input_sample", "")
            if scenario_input:
                result = bootstrap_scenario_input(created["session_id"], scenario_input)
                _append_bootstrap_exchange(scenario_input, result)
                refresh_flags()
                refresh_actions()
    except ApiError as exc:
        if created is not None:
            # 会话已创建但首轮消息失败：标记已加载，避免每次 rerun 重复建会话。
            st.session_state.loaded_scenario_label = selected_scenario_label
        show_api_error(exc)
        return
    st.session_state.loaded_scenario_label = selected_scenario_label
    st.rerun()


def create_blank_session() -> None:
    try:
        with st.spinner("创建中..."):
            created = create_session()
    except ApiError as exc:
        show_api_error(exc)
        return
    _activate_created_session(created)
    st.session_state.reset_scenario_selector = True
    st.rerun()


def select_session(session: dict) -> None:
    """先成功读取目标会话，再原子切换；失败保持当前会话不变。"""
    target_id = session.get("session_id")
    ok, ctx = get_session_checked(target_id) if target_id else (False, None)
    if not ok or not isinstance(ctx, dict):
        st.session_state.session_load_error = (
            f"无法加载会话 {target_id}；当前会话保持不变，请再次点击该会话重试。"
        )
        st.rerun()
        return

    actions_ok, actions = list_actions_checked(target_id, status="pending")
    readiness_ok, readiness = get_stage_readiness_checked(target_id)
    interrupts_ok, interrupts = list_interrupt_records_checked(target_id)

    st.session_state.session_id = target_id
    st.session_state.current_state = (
        ctx.get("current_state") or session.get("current_state") or "init"
    )
    st.session_state.selected_scenario_id = ctx.get("selected_scenario_id")
    st.session_state.messages = restore_messages_from_ctx(ctx)
    st.session_state.pending_flags = [
        f for f in ctx.get("flagged_items", []) if f["status"] == "pending"
    ]
    st.session_state.pending_actions = (
        actions
        if actions_ok and isinstance(actions, list)
        else [a for a in ctx.get("pending_actions", []) if a["status"] == "pending"]
    )
    st.session_state.interrupt_records = (
        interrupts if interrupts_ok and isinstance(interrupts, list) else []
    )
    st.session_state.stage_readiness = readiness if readiness_ok else {}
    st.session_state.session_load_error = ""
    st.session_state.session_read_error = ""
    st.session_state.advancement_error = ""
    st.session_state.actions_error = (
        "" if actions_ok else "无法读取待处理人工动作，当前显示可能不是最新结果。"
    )
    st.session_state.readiness_error = (
        "" if readiness_ok else "无法读取阶段门禁状态，当前显示可能不是最新结果。"
    )
    # 切换会话必须丢弃上一会话的派生门禁状态与未发送草稿。
    st.session_state.stage_resolution = {}
    st.session_state.stage_advancement_decisions = {}
    st.session_state.stage_advancement_decision = None
    st.session_state.pop("chat_retry_draft", None)
    clear_flash()
    st.rerun()


def rename_session_event(session_id: str, name: str) -> None:
    try:
        renamed = rename_session(session_id, name)
    except ApiError as exc:
        show_api_error(exc)
        return
    st.toast(f"会话已重命名为：{renamed['session_name']}")
    st.rerun()


def delete_session(session_id: str) -> dict:
    result = api_delete(f"/sessions/{session_id}")
    invalidate_api_cache("sessions:")
    invalidate_session_cache(session_id)
    return result


def refresh_current_session() -> None:
    """手动刷新：清空前端读取缓存，并重新拉取当前会话的完整状态。"""
    invalidate_api_cache()
    session_id = st.session_state.session_id
    if session_id:
        ok, ctx = get_session_checked(session_id)
        if not ok or not isinstance(ctx, dict):
            st.session_state.session_load_error = (
                "刷新失败：无法读取当前会话，已保留原有内容，请稍后重试。"
            )
        else:
            st.session_state.session_load_error = ""
            st.session_state.current_state = (
                ctx.get("current_state") or st.session_state.current_state
            )
            st.session_state.selected_scenario_id = ctx.get("selected_scenario_id")
            st.session_state.messages = restore_messages_from_ctx(ctx)
            st.session_state.pending_flags = [
                f for f in ctx.get("flagged_items", []) if f["status"] == "pending"
            ]
            st.session_state.pending_actions = [
                a for a in ctx.get("pending_actions", []) if a["status"] == "pending"
            ]
        refresh_actions()
    st.rerun()


def add_materials(materials: list[str]) -> bool:
    try:
        with st.spinner("上传中..."):
            add_materials_to_session(st.session_state.session_id, materials)
    except ApiError as exc:
        show_api_error(exc)
        return False
    st.warning("✅ 资料已追加。阶段分析已过期，工作流将从阶段一开始重新评估。")
    refresh_flags()
    refresh_actions()
    st.rerun()
    return True


def recover_workflow(target_state: str, note: str = "") -> None:
    """从阻断态显式恢复到可推进状态，并同步前端状态。"""
    try:
        with st.spinner("正在恢复工作流..."):
            result = recover_workflow_api(
                st.session_state.session_id,
                target_state,
                note,
            )
    except ApiError as exc:
        show_api_error(exc)
        return
    st.session_state.current_state = result["after"]
    st.toast(f"工作流已恢复到：{result['after']}")
    refresh_flags()
    refresh_actions()
    st.rerun()


def handle_send(user_input: str, materials: list[str] | None = None) -> None:
    """
    统一处理发送消息的逻辑：
    追加用户消息 → 调用 API → 追加 AI 回复 → 刷新状态。

    失败时按"明确拒绝"与"结果未知"区分标记，由视图渲染状态，不自动重发。
    """
    message = {
        "role": "user",
        "content": user_input,
        "metadata": {"delivery_status": "sending"},
    }
    st.session_state.messages.append(message)

    try:
        with st.spinner("🤖 AI 思考中，请稍候..."):
            result = send_message(
                session_id=st.session_state.session_id,
                user_input=user_input,
                materials=materials,
            )
    except ApiError as exc:
        _mark_delivery_failure(message, user_input, exc)
        return

    message["metadata"]["delivery_status"] = "confirmed"
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result["ai_reply"],
            "metadata": {},
        }
    )
    st.session_state.current_state = result["current_state"]
    st.session_state.pop("chat_retry_draft", None)
    clear_flash()
    refresh_flags()
    refresh_actions()


def _mark_delivery_failure(message: dict, user_input: str, exc: ApiError) -> None:
    """把失败写回用户消息状态；跨 rerun 的提示通过 flash 保留。"""
    reason = describe_api_error(exc)
    if _outcome_is_unknown(exc):
        message["metadata"]["delivery_status"] = "unknown"
        set_flash(
            "warning",
            "消息结果未知：服务端可能已处理，请刷新核对；不会自动重发。",
        )
        return
    message["metadata"]["delivery_status"] = "failed"
    message["metadata"]["delivery_error"] = reason
    st.session_state.pop("chat_retry_edit", None)
    st.session_state.chat_retry_draft = user_input
    set_flash("error", f"消息未发送：{reason}")
