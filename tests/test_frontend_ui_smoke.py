"""前端页面 AppTest 冒烟测试：离线依赖下工作台与治理总览可渲染。"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
APP_PATH = FRONTEND_DIR / "app.py"

if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

_GOVERNANCE_TREND = [
    {
        "week": "2026-W44",
        "pass_rate": 0.66,
        "evaluations": 3,
        "passed": 2,
        "top_blocking_rules": [],
    }
]

_ROUTES: dict[str, object] = {
    "/health": {
        "status": "ok",
        "workflow_execution_mode": "single_step",
        "interrupt_adapter_status": "unknown",
    },
    "/sessions/scenarios": [],
    "/sessions/": [],
    "/governance/overview": {
        "sessions_total": 0,
        "pending_actions": 0,
        "open_safety_findings": 0,
        "reports_exported": 0,
        "excluded_demo_sessions": 0,
        "state_distribution": {"init": 1},
        "risk_tier_distribution": {},
    },
    "/governance/gate-trends": _GOVERNANCE_TREND,
    "/governance/actions-backlog": [],
}


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _FakeHttpSession:
    """最小假传输层：只回答前端只读 GET，测试内不触达真实后端。"""

    def __init__(self) -> None:
        self.requested_paths: list[str] = []

    def get(self, url: str, headers=None, timeout=None) -> _FakeResponse:
        path = urlparse(url).path
        self.requested_paths.append(path)
        return _FakeResponse(_ROUTES.get(path))

    def post(self, url: str, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse({})

    def patch(self, url: str, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse({})

    def delete(self, url: str, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse({})


@pytest.fixture
def offline_api(monkeypatch: pytest.MonkeyPatch) -> _FakeHttpSession:
    import models.api_client as api_client

    fake = _FakeHttpSession()
    # 所有 api_* 函数都通过模块级 _http_session 取数，替换该对象即可覆盖全链路。
    monkeypatch.setattr(api_client, "_http_session", fake)
    return fake


_GOVERNANCE_SCRIPT = f"""
import sys
sys.path.insert(0, {str(FRONTEND_DIR)!r})

import streamlit as st
from models.session_state import init_session_state
from views.pages import render_governance_page

st.set_page_config(page_title="governance-smoke", layout="wide")
init_session_state()
render_governance_page()
"""


def _seed_auth(at: AppTest) -> None:
    at.session_state["access_token"] = "test-token"
    at.session_state["user_role"] = "admin"


def test_workbench_page_renders_without_backend(offline_api: _FakeHttpSession):
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    _seed_auth(at)
    at.run()

    assert not at.exception
    assert any("欢迎使用" in el.value for el in at.markdown)
    assert len(at.error) == 0
    assert "/health" in offline_api.requested_paths
    assert "/sessions/" in offline_api.requested_paths


def test_governance_page_renders_sparse_data_without_backend(offline_api: _FakeHttpSession):
    at = AppTest.from_string(_GOVERNANCE_SCRIPT, default_timeout=20)
    _seed_auth(at)
    at.run()

    assert not at.exception
    assert any(el.value == "治理总览" for el in at.header)
    info_values = [el.value for el in at.info]
    assert any("当前暂无真实业务会话数据" in value for value in info_values)
    assert any("数据不足以形成趋势线" in value for value in info_values)
    assert any("无积压动作。" in value for value in info_values)
    assert len(at.error) == 0
    assert "/governance/overview" in offline_api.requested_paths
    assert "/governance/gate-trends" in offline_api.requested_paths
    assert "/governance/actions-backlog" in offline_api.requested_paths
