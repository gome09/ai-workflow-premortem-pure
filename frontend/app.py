# frontend/app.py
from __future__ import annotations

import streamlit as st
from controllers.auth_controller import ensure_auth
from models.session_state import init_session_state
from views.pages import render_governance_page, render_workbench_page

st.set_page_config(
    page_title="AI 工作流风险复核工作台",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_auth()
init_session_state()
pages = st.navigation(
    [
        st.Page(render_workbench_page, title="会话工作台", icon="🗂️", default=True),
        st.Page(render_governance_page, title="治理总览", icon="📊"),
    ],
    position="sidebar",
)
pages.run()
