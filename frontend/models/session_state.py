# frontend/models/session_state.py
from __future__ import annotations

import streamlit as st

from models.api_client import (
    get_session_checked,
    get_stage_readiness_checked,
    invalidate_session_cache,
    list_actions_checked,
    list_interrupt_records_checked,
)


def _clear_read_errors() -> None:
    st.session_state.session_read_error = ""
    st.session_state.actions_error = ""
    st.session_state.readiness_error = ""
    st.session_state.advancement_error = ""


def restore_messages_from_ctx(ctx: dict) -> list[dict]:
    """
    从 API 返回的 ctx 中还原展示用的消息列表。
    过滤 system / tool 角色消息，按阶段顺序排列。
    """
    messages = []
    history = ctx.get("conversation_history", {})
    for stage_key in sorted(history.keys()):
        for msg in history[stage_key]:
            if msg["role"] in ("system", "tool"):
                continue
            messages.append(
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    "metadata": msg.get("metadata", {}),
                }
            )
    return messages


def _reset_session_state() -> None:
    """删除当前会话后清空会话相关状态，回到「新建会话」初始界面。"""
    st.session_state.session_id = None
    st.session_state.current_state = "init"
    st.session_state.messages = []
    st.session_state.pending_flags = []
    st.session_state.pending_actions = []
    st.session_state.interrupt_records = []
    st.session_state.stage_readiness = {}
    st.session_state.stage_resolution = {}
    st.session_state.stage_advancement_decision = None
    st.session_state.stage_advancement_decisions = {}
    st.session_state.next_required_operation = None
    st.session_state.selected_scenario_id = None
    st.session_state.reset_scenario_selector = True
    st.session_state.session_load_error = ""
    st.session_state.session_extra_pages = []
    st.session_state.session_list_end = False
    st.session_state.eval_run_keys = {}
    st.session_state.eval_run_modes = {}
    st.session_state.eval_experiment_status = {}
    st.session_state.eval_status_failures = {}
    st.session_state.report_list_limit = 20
    st.session_state.calibration_limit = 20
    st.session_state.chat_retry_draft = ""
    st.session_state.pop("_flash", None)
    _clear_read_errors()


def _activate_created_session(created: dict) -> None:
    """把新建会话切换为当前会话，并清空上一会话的前端派生状态。"""
    st.session_state.session_id = created["session_id"]
    st.session_state.selected_scenario_id = created.get("selected_scenario_id")
    st.session_state.messages = []
    st.session_state.current_state = created.get("current_state", "init")
    st.session_state.pending_flags = []
    st.session_state.pending_actions = []
    st.session_state.interrupt_records = []
    st.session_state.stage_readiness = {}
    st.session_state.stage_resolution = {}
    st.session_state.stage_advancement_decision = None
    st.session_state.stage_advancement_decisions = {}
    st.session_state.next_required_operation = None
    st.session_state.session_load_error = ""
    st.session_state.chat_retry_draft = ""
    st.session_state.pop("_flash", None)
    _clear_read_errors()


def _append_bootstrap_exchange(scenario_input: str, result: dict) -> None:
    """将内置场景的样例输入与首轮回复呈现为正常会话消息。"""
    st.session_state.messages = [
        {"role": "user", "content": scenario_input, "metadata": {}},
        {"role": "assistant", "content": result["ai_reply"], "metadata": {}},
    ]
    st.session_state.current_state = result["current_state"]


def init_session_state() -> None:
    defaults = {
        "session_id": None,
        "selected_scenario_id": None,
        "selected_scenario_label": None,
        "loaded_scenario_label": None,
        "messages": [],
        "current_state": "init",
        "pending_flags": [],
        "pending_actions": [],
        "interrupt_records": [],
        "stage_readiness": {},
        "stage_resolution": {},
        "stage_advancement_decision": {},
        "stage_advancement_decisions": {},
        "next_required_operation": None,
        "health": {},
        "is_loading": False,
        "handled_session_events": {},
        "session_load_error": "",
        "session_read_error": "",
        "actions_error": "",
        "readiness_error": "",
        "advancement_error": "",
        "session_extra_pages": [],
        "session_list_end": False,
        "eval_run_keys": {},
        "eval_run_modes": {},
        "eval_experiment_status": {},
        "eval_status_failures": {},
        "report_list_limit": 20,
        "calibration_limit": 20,
        "chat_retry_draft": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def consume_session_event(event: dict | None) -> dict | None:
    """每个会话组件事件只处理一次，避免 Streamlit rerun 后重复提交。"""
    if not isinstance(event, dict):
        return None
    session_id = str(event.get("session_id", ""))
    nonce = event.get("nonce")
    if not session_id or nonce is None:
        return None
    handled = dict(st.session_state.get("handled_session_events", {}))
    if handled.get(session_id) == nonce:
        return None
    handled[session_id] = nonce
    st.session_state.handled_session_events = handled
    return event


def refresh_flags() -> None:
    if not st.session_state.session_id:
        return
    invalidate_session_cache(st.session_state.session_id)
    ok, ctx = get_session_checked(st.session_state.session_id)
    if not ok or not isinstance(ctx, dict):
        st.session_state.session_read_error = "无法读取会话状态，当前显示可能不是最新结果。"
        return
    st.session_state.session_read_error = ""
    st.session_state.pending_flags = [
        f for f in ctx.get("flagged_items", []) if f["status"] == "pending"
    ]
    st.session_state.pending_actions = [
        a for a in ctx.get("pending_actions", []) if a["status"] == "pending"
    ]


def refresh_actions() -> None:
    if not st.session_state.session_id:
        return
    invalidate_session_cache(st.session_state.session_id)
    actions_ok, actions = list_actions_checked(
        st.session_state.session_id,
        status="pending",
    )
    readiness_ok, readiness = get_stage_readiness_checked(st.session_state.session_id)
    interrupts_ok, interrupts = list_interrupt_records_checked(st.session_state.session_id)

    if actions_ok and isinstance(actions, list):
        st.session_state.pending_actions = actions
        st.session_state.actions_error = ""
    else:
        st.session_state.actions_error = "无法读取待处理人工动作，当前显示可能不是最新结果。"
    if readiness_ok and isinstance(readiness, dict):
        st.session_state.stage_readiness = readiness
        st.session_state.readiness_error = ""
    else:
        st.session_state.readiness_error = "无法读取阶段门禁状态，当前显示可能不是最新结果。"
    if interrupts_ok and isinstance(interrupts, list):
        st.session_state.interrupt_records = interrupts
    # 推进判定依赖被刷新的门禁状态，旧值必须丢弃，由面板在下次渲染时回源。
    if actions_ok or readiness_ok:
        st.session_state.stage_advancement_decisions = {}
        st.session_state.stage_advancement_decision = None
