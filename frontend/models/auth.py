# frontend/models/auth.py
from __future__ import annotations

import base64
import json

import requests
import streamlit as st

from models.config import API_BASE, DEMO_USER_EMAIL, DEMO_USER_PASSWORD


def _login_demo_user() -> dict | None:
    try:
        r = requests.post(
            f"{API_BASE}/auth/login",
            data={"username": DEMO_USER_EMAIL, "password": DEMO_USER_PASSWORD},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException:
        return None


def _register_demo_user() -> dict | None:
    try:
        r = requests.post(
            f"{API_BASE}/auth/register",
            json={"email": DEMO_USER_EMAIL, "password": DEMO_USER_PASSWORD},
            timeout=10,
        )
        # 409=已存在、429=注册限流：都回退到登录，避免演示账号被限流卡死
        if r.status_code in (409, 429):
            return _login_demo_user()
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException:
        return None


def _refresh_access_token() -> bool:
    refresh_token = st.session_state.get("refresh_token")
    if not refresh_token:
        return False
    try:
        r = requests.post(
            f"{API_BASE}/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=10,
        )
        r.raise_for_status()
        st.session_state.access_token = r.json().get("access_token")
        return True
    except requests.exceptions.RequestException:
        return False


def _role_from_token(token: str) -> str:
    """从 JWT access token payload 解析角色（本地解码，无需网络请求）。"""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # 补齐 base64 padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("role", "")
    except Exception:
        return ""


def _auth_headers() -> dict:
    token = st.session_state.get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}
