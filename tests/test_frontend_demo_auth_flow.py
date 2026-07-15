# tests/test_frontend_demo_auth_flow.py
"""回归测试：前端演示账号的自动登录/注册顺序。

/auth/register 限流是 5/hour（见 auth/router.py），而 /auth/login 是
10/minute。demo 账号在第一次成功引导后就已经存在，此后每次 Streamlit
重跑本该走登录这条常见路径，而不是重新尝试注册。

旧版 ensure_auth() 直接调用 _register_demo_user()（仅在返回 409 时才回退
登录），导致 demo 账号已存在的情况下，每一次脚本重跑都会消耗一次宝贵的
注册配额；只要短时间内刷新几次页面（或后端/前端重启导致 session_state
清空后重新走一遍），5/hour 配额就会耗尽，进而让 register 返回 429、
ensure_auth 静默拿不到 token，之后所有需要鉴权的接口都会报 401——这正是
实际观察到的故障现象。

修复：ensure_auth 优先尝试登录，只有登录失败时才回退到注册。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))

import app  # noqa: E402


def test_ensure_auth_tries_login_before_register(monkeypatch):
    app.st.session_state.clear()
    calls = []

    monkeypatch.setattr(
        app,
        "_login_demo_user",
        lambda: (calls.append("login"), {"access_token": "tok-from-login"})[1],
    )
    monkeypatch.setattr(
        app,
        "_register_demo_user",
        lambda: (calls.append("register"), {"access_token": "tok-from-register"})[1],
    )

    app.ensure_auth()

    assert calls == ["login"], f"登录成功时不应再调用注册接口，实际调用顺序={calls!r}"
    assert app.st.session_state["access_token"] == "tok-from-login"


def test_ensure_auth_falls_back_to_register_when_login_fails(monkeypatch):
    app.st.session_state.clear()
    calls = []

    monkeypatch.setattr(app, "_login_demo_user", lambda: (calls.append("login"), None)[1])
    monkeypatch.setattr(
        app,
        "_register_demo_user",
        lambda: (calls.append("register"), {"access_token": "tok-from-register"})[1],
    )

    app.ensure_auth()

    assert calls == ["login", "register"]
    assert app.st.session_state["access_token"] == "tok-from-register"


def test_ensure_auth_skips_network_calls_when_token_already_present(monkeypatch):
    app.st.session_state.clear()
    app.st.session_state["access_token"] = "existing-token"

    def _fail(*_a, **_k):
        raise AssertionError("已有 token 时不应再发起登录/注册请求")

    monkeypatch.setattr(app, "_login_demo_user", _fail)
    monkeypatch.setattr(app, "_register_demo_user", _fail)

    app.ensure_auth()

    assert app.st.session_state["access_token"] == "existing-token"
