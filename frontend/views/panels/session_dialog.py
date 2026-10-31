# frontend/views/panels/session_dialog.py
from __future__ import annotations

import streamlit as st
from controllers.session_controller import delete_session
from models.mappings import STATE_LABELS
from models.session_state import _reset_session_state


@st.dialog("确认删除会话")
def confirm_delete_session(
    session_id: str, label: str, current_state: str, is_current: bool
) -> None:
    state_icon, state_label = STATE_LABELS.get(current_state, ("⚪", "未知"))
    st.markdown(f"即将删除会话：**{label}**")
    st.caption(f"状态：{state_icon} {state_label}　·　`{session_id}`")
    st.warning(
        "删除后该会话的四阶段输出、证据、评测与红队数据将被级联清除，"
        "审计事件将归档保留。此操作不可撤销。"
    )
    if is_current:
        st.info("这是当前正在使用的会话，删除后将回到「新建会话」初始状态。")

    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button("🗑️ 确认删除", type="primary", use_container_width=True):
            result = delete_session(session_id)
            if result is not None:
                if is_current:
                    _reset_session_state()
                st.toast(f"会话已删除：{label[:20]}")
                st.rerun()
    with col_cancel:
        if st.button("取消", use_container_width=True):
            st.rerun()
