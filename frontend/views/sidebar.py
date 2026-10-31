# frontend/views/sidebar.py
from __future__ import annotations

import streamlit as st
from components.session_item import render_session_item
from controllers.session_controller import (
    create_blank_session,
    load_builtin_scenario,
    refresh_current_session,
    rename_session_event,
    select_session,
)
from labels import adapter_status_zh, exec_mode_zh
from models.api_client import (
    get_builtin_scenario,
    get_health,
    list_builtin_scenarios,
    list_sessions,
)
from models.mappings import MODEL_LABELS, STAGE_PROGRESS, STATE_LABELS
from models.session_state import consume_session_event

from views.panels.diagnostics_panel import render_audit_panel, render_interrupt_panel
from views.panels.eval_panels import render_eval_panel, render_redteam_section
from views.panels.gate_panel import render_gate_panel
from views.panels.governance_panels import (
    render_action_queue,
    render_evidence_panel,
    render_flags_panel,
    render_safety_panel,
)
from views.panels.report_workspace import render_report_workspace
from views.panels.session_dialog import confirm_delete_session


def render_sidebar() -> None:
    with st.sidebar:
        st.title("🔬 AI 工作流工具")
        st.caption("项目立项失败模式分析")
        st.session_state.health = get_health()
        if st.session_state.health:
            st.caption(
                f"执行模式：{exec_mode_zh(st.session_state.health.get('workflow_execution_mode', 'unknown'))}"
                f" · 中断适配器：{adapter_status_zh(st.session_state.health.get('interrupt_adapter_status', 'unknown'))}"
            )

        # ── 页面导航由 app.py 的 st.navigation 负责，侧栏只渲染当前页内容 ─────────
        st.divider()

        if st.session_state.get("active_page", "workbench") == "workbench":
            _render_session_management()
            st.divider()

            if st.session_state.session_id:
                _render_current_progress()
        else:
            st.info("📊 治理总览模式")
            st.caption("请在主区域查看全局治理数据")


def _render_session_management() -> None:
    st.subheader("📋 会话管理")

    scenarios = list_builtin_scenarios()
    scenario_placeholder = "选择内置场景"
    scenario_options = {}
    for item in scenarios:
        scenario_options[item.get("name", "未命名场景")] = item.get("scenario_id")

    # 「新建空白会话」在上一次渲染中设置复位标记；必须在创建 widget 前
    # 改写其 key，避免 Streamlit 的 widget-state mutation 异常。
    if st.session_state.pop("reset_scenario_selector", False):
        st.session_state.selected_scenario_label = None
        st.session_state.loaded_scenario_label = None
    if (
        st.session_state.get("selected_scenario_label") is not None
        and st.session_state.selected_scenario_label not in scenario_options
    ):
        st.session_state.selected_scenario_label = None

    col_scenario, col_refresh = st.columns([3, 2], vertical_alignment="bottom")
    with col_scenario:
        selected_scenario_label = st.selectbox(
            "内置场景",
            options=list(scenario_options.keys()),
            index=None,
            placeholder=scenario_placeholder,
            key="selected_scenario_label",
            help="选择后会立即创建会话，并把该场景的样例输入加载到主工作区。",
            label_visibility="collapsed",
            accept_new_options=False,
            filter_mode=None,
        )
    with col_refresh:
        if st.button("🔄 刷新", use_container_width=True):
            refresh_current_session()

    selected_scenario_id = (
        scenario_options.get(selected_scenario_label) if selected_scenario_label else None
    )

    if not selected_scenario_id:
        st.session_state.loaded_scenario_label = None

    if selected_scenario_id:
        scenario_detail = get_builtin_scenario(selected_scenario_id)
        if scenario_detail:
            st.caption(scenario_detail.get("description", ""))
            st.caption(
                f"领域配置=`{scenario_detail.get('domain_profile')}` · "
                f"模拟数据=`{scenario_detail.get('mock_fixture')}`"
            )
            with st.expander("查看场景样例输入", expanded=False):
                st.code(scenario_detail.get("input_sample", ""), language="markdown")
    else:
        scenario_detail = None

    # 下拉选择本身就是「加载场景」动作：创建绑定场景的会话并自动发送
    # 样例输入，使主工作区呈现与正常会话完全一致的用户/助手消息。
    load_builtin_scenario(selected_scenario_id, scenario_detail, selected_scenario_label)

    st.html("<style>.st-key-create_blank_session button p { white-space: nowrap; }</style>")
    if st.button("➕ 新建空白会话", use_container_width=True, key="create_blank_session"):
        create_blank_session()

    _render_session_list()


def _render_session_list() -> None:
    sessions = list_sessions()
    is_admin = st.session_state.get("user_role") == "admin"
    if sessions:
        st.caption(f"最近 {len(sessions)} 个会话")
        for s in sessions[:10]:
            icon, state_label = STATE_LABELS.get(s["current_state"], ("⚪", ""))
            raw_label = (
                s.get("session_name")
                or s.get("research_target")
                or s.get("scenario_name")
                or "未命名会话"
            )
            domain = s.get("domain") or ""

            # 高亮当前会话
            is_current = s["session_id"] == st.session_state.session_id

            session_event = consume_session_event(
                render_session_item(
                    session_id=s["session_id"],
                    label=raw_label,
                    icon=icon,
                    state_label=state_label,
                    domain=domain,
                    is_current=is_current,
                    disabled=st.session_state.get("user_role") == "viewer",
                    can_delete=is_admin,
                )
            )
            if session_event and session_event.get("action") == "rename":
                rename_session_event(s["session_id"], session_event.get("name", ""))
            elif session_event and session_event.get("action") == "delete":
                confirm_delete_session(
                    s["session_id"],
                    raw_label,
                    s.get("current_state", ""),
                    is_current,
                )
            elif session_event and session_event.get("action") == "select":
                select_session(s)
    else:
        st.caption("暂无历史会话")


def _render_current_progress() -> None:
    st.subheader("📊 当前进度")
    if st.session_state.selected_scenario_id:
        st.caption(f"当前场景：`{st.session_state.selected_scenario_id}`")

    state = st.session_state.current_state
    icon, label = STATE_LABELS.get(state, ("⚪", "未知"))
    progress = STAGE_PROGRESS.get(state, 0)
    model = MODEL_LABELS.get(state, "")

    st.markdown(f"**{icon} {label}**")
    st.progress(progress / 100)
    st.caption(f"进度 {progress}%　·　{model}")

    # 四个阶段的状态指示
    stage_cols = st.columns(4)
    stage_defs = [
        ("一", ["s1_running", "s1_review"]),
        ("二", ["s2_running", "s2_review"]),
        ("三", ["s3_running", "s3_review"]),
        ("四", ["s4_running", "s4_review"]),
    ]
    for i, (name, stage_states) in enumerate(stage_defs):
        with stage_cols[i]:
            current_progress = STAGE_PROGRESS.get(state, 0)
            stage_end_progress = STAGE_PROGRESS.get(stage_states[-1], 0)
            if state in stage_states:
                st.markdown(f"**🔵{name}**")
            elif current_progress > stage_end_progress:
                st.markdown(f"✅{name}")
            else:
                st.markdown(f"⚪{name}")

    render_gate_panel(state)

    st.divider()

    # ── Human Oversight 动作队列 ───────────────────────────────────────────
    render_action_queue()

    st.divider()

    # ── 【需核验】面板 ─────────────────────────────────────────────────────
    render_flags_panel()

    st.divider()

    # ── Evidence / Safety 面板 ──────────────────────────────────────────────
    render_evidence_panel()
    render_safety_panel()
    render_interrupt_panel()
    render_redteam_section()
    render_eval_panel()

    st.divider()

    # ── 审计历史 ───────────────────────────────────────────────────────────
    render_audit_panel()

    st.divider()

    # ── 报告面板 ───────────────────────────────────────────────────────────
    render_report_workspace()
