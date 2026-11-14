# frontend/controllers/auth_controller.py
from __future__ import annotations

import requests
import streamlit as st
from models.api_client import accept_invitation
from models.auth import _login_demo_user, _register_demo_user, _role_from_token
from models.config import API_BASE, DEMO_AUTO_AUTH
from models.feedback import ApiError, show_api_error


def ensure_auth() -> None:
    notice = st.session_state.pop("auth_notice", "")
    if notice:
        st.warning(notice)
    if st.session_state.get("access_token"):
        # 角色以当前 token 的 JWT payload 为准（login 响应体不含 role 字段）
        st.session_state.user_role = _role_from_token(st.session_state.access_token)
        return
    if DEMO_AUTO_AUTH:
        if notice:
            # 终端失效后不能继续自动登录，否则会形成 401 → 自动登录循环。
            st.error("演示账号登录凭据已失效，自动登录已暂停。")
            if st.button("重新登录演示账号", key="demo_relogin"):
                st.rerun()
            st.stop()
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

        with st.expander("使用邀请码加入工作区", expanded=False):
            invite_token = st.text_input("邀请码", key="invitation_token_input")
            invite_password = st.text_input(
                "设置密码",
                type="password",
                key="invitation_password_input",
            )
            if st.button("接受邀请并登录", key="accept_invitation_button"):
                if not invite_token.strip() or not invite_password:
                    st.error("邀请码与密码均为必填。")
                else:
                    try:
                        invitation_result = accept_invitation(invite_token.strip(), invite_password)
                    except ApiError as exc:
                        show_api_error(exc)
                        invitation_result = None
                    if invitation_result and invitation_result.get("access_token"):
                        tokens = invitation_result
    if tokens and tokens.get("access_token"):
        st.session_state.access_token = tokens["access_token"]
        st.session_state.refresh_token = tokens.get("refresh_token")
        st.session_state.user_role = _role_from_token(tokens["access_token"])
        st.session_state.pop("auth_notice", None)
        st.rerun()
    if not st.session_state.get("access_token"):
        st.stop()
