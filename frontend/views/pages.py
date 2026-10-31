# frontend/views/pages.py
"""st.navigation 页面装配：页面函数负责标记当前页并渲染侧栏与主区域。"""

from __future__ import annotations

import streamlit as st
from components.governance_overview import render_governance_overview

from views.sidebar import render_sidebar
from views.workbench import render_workbench


def render_workbench_page() -> None:
    st.session_state.active_page = "workbench"
    render_sidebar()
    render_workbench()


def render_governance_page() -> None:
    st.session_state.active_page = "governance"
    render_sidebar()
    render_governance_overview()
