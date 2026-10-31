# frontend/controllers/auth_controller.py
from __future__ import annotations

import requests
import streamlit as st
from models.auth import _login_demo_user, _register_demo_user, _role_from_token
from models.config import API_BASE, DEMO_AUTO_AUTH


def ensure_auth() -> None:
    if st.session_state.get("access_token"):
        # 角色以当前 token 的 JWT payload 为准（login 响应体不含 role 字段）
        st.session_state.user_role = _role_from_token(st.session_state.access_token)
        return
    if DEMO_AUTO_AUTH:
        # 仅显式启用的演示环境使用固定账号：先登录，失败再注册。
        tokens = _login_demo_user() or _register_demo_user()
    else:
        st.title("登录 AI 工作流风险复核工作台")
        with st.form("interactive_login"):
            email = st.text_input("邮箱")
            password = st.text_input("密码", type="password")
            register = st.checkbox("首次使用：注册新工作区")
            submitted = st.form_submit_button("注册并登录" if register else "登录")
        tokens = None
        if submitted and email and password:
            if register:
                try:
                    response = requests.post(
                        f"{API_BASE}/auth/register",
                        json={"email": email, "password": password},
                        timeout=10,
                    )
                except requests.exceptions.RequestException:
                    response = None
            else:
                try:
                    response = requests.post(
                        f"{API_BASE}/auth/login",
                        data={"username": email, "password": password},
                        timeout=10,
                    )
                except requests.exceptions.RequestException:
                    response = None
            if response is not None and response.ok:
                tokens = response.json()
            else:
                detail = "无法连接认证服务"
                if response is not None:
                    try:
                        detail = response.json().get("detail", "认证失败")
                    except ValueError:
                        detail = "认证失败"
                st.error(detail)
    if tokens and tokens.get("access_token"):
        st.session_state.access_token = tokens["access_token"]
        st.session_state.refresh_token = tokens.get("refresh_token")
        st.session_state.user_role = _role_from_token(tokens["access_token"])
        st.rerun()
    if not st.session_state.get("access_token"):
        st.stop()
