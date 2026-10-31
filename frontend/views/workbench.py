# frontend/views/workbench.py
from __future__ import annotations

import streamlit as st
from components.governance_overview import render_governance_overview
from controllers.session_controller import add_materials, handle_send
from models.config import API_BASE
from models.mappings import CHAT_PLACEHOLDER

from views.live_oversight import render_message_with_oversight
from views.welcome import render_welcome


def render_workbench() -> None:
    if st.session_state.get("nav_page") == "治理总览":
        token = st.session_state.get("access_token") or ""
        render_governance_overview(API_BASE, token)
    elif not st.session_state.session_id:
        render_welcome()
    else:
        _render_chat_workspace()


def _render_chat_workspace() -> None:
    # 渲染对话历史
    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]
        metadata = msg.get("metadata", {})
        reasoning = metadata.get("reasoning", "")

        if role == "assistant":
            with st.chat_message("assistant", avatar="🤖"):
                if reasoning:
                    with st.expander("🧠 查看推理过程（DeepSeek V4 thinking）", expanded=False):
                        st.markdown(reasoning)
                render_message_with_oversight(content)

        elif role == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(content)

    # ── 资料上传区 ────────────────────────────────────────────────────────────
    with st.expander("📎 补充参考资料（可选）", expanded=False):
        st.caption(
            "粘贴文档、研究报告、使用经验等，AI 将在下一轮分析中参考这些内容。"
            "资料添加后立即生效，无需重新发送消息。"
        )

        material_text = st.text_area(
            "粘贴文本内容",
            height=100,
            placeholder="粘贴任意文本...",
            key="material_text_input",
        )
        uploaded_file = st.file_uploader(
            "或上传文件（.txt / .md）",
            type=["txt", "md"],
            key="file_uploader",
        )

        if st.button("✅ 添加到本次分析", use_container_width=True):
            materials: list[str] = []
            if material_text.strip():
                materials.append(material_text.strip())
            if uploaded_file is not None:
                file_content = uploaded_file.read().decode("utf-8", errors="ignore")
                materials.append(f"[文件：{uploaded_file.name}]\n{file_content}")

            if materials:
                add_materials(materials)
            else:
                st.warning("请先输入或上传资料内容。")

    # ── 快捷操作按钮（仅在 review 状态显示）────────────────────────────────
    state = st.session_state.current_state
    review_states = {"s1_review", "s2_review", "s3_review", "s4_review"}

    if state in review_states:
        st.markdown("---")
        st.markdown("**⚡ 快捷操作**")

        # 基础三个操作
        quick_cols = st.columns(4)
        quick_actions = [
            (quick_cols[0], "✅ 确认，进入下一阶段", "确认"),
            (quick_cols[1], "⬅️ 回退上一阶段", "回退"),
        ]

        # 阶段三额外提供「回退工作流」
        if state == "s3_review":
            quick_actions.append((quick_cols[2], "🔁 回退到工作流设计", "回退工作流"))

        for col, btn_label, action_text in quick_actions:
            with col:
                if st.button(btn_label, use_container_width=True):
                    handle_send(action_text)
                    st.rerun()

    # ── 输入框 ────────────────────────────────────────────────────────────────
    placeholder = CHAT_PLACEHOLDER.get(state, "输入消息...")
    disabled = state == "complete"

    if user_input := st.chat_input(placeholder, disabled=disabled):
        handle_send(user_input)
        st.rerun()
