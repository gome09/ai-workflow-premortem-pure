# frontend/app.py
from __future__ import annotations

import streamlit as st
from controllers.auth_controller import ensure_auth
from models.session_state import init_session_state
from views.sidebar import render_sidebar
from views.workbench import render_workbench

st.set_page_config(
    page_title="AI 工作流风险复核工作台",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_auth()
init_session_state()
render_sidebar()
render_workbench()
