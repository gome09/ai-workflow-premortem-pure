# tests/test_frontend_session_delete.py
"""侧栏「会话删除」功能的前端契约测试。

frontend/app.py 只是入口装配，具体逻辑位于 frontend/models 与
frontend/controllers。这里扫描 frontend/**/*.py 聚合源码做契约断言：
  1) AST 源码契约：断言 api_delete / 删除按钮 / 确认弹窗的关键结构存在且
     角色门控正确；
  2) 函数抽取执行：把纯逻辑函数 _role_from_token / _reset_session_state
     从源码中抽出，在受控命名空间里真实执行，验证行为。
"""

from __future__ import annotations

import ast
import base64
import json
from pathlib import Path
from types import SimpleNamespace

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_SOURCES = {
    path: path.read_text(encoding="utf-8") for path in sorted(FRONTEND_DIR.rglob("*.py"))
}
SOURCE = "\n".join(FRONTEND_SOURCES.values())
FRONTEND_TREES = {path: ast.parse(src) for path, src in FRONTEND_SOURCES.items()}


def _extract_function(name: str) -> tuple[ast.FunctionDef, Path]:
    for path, tree in FRONTEND_TREES.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node, path
    raise AssertionError(f"frontend/**/*.py 中未找到函数 {name}")


def _exec_function(name: str, extra_globals: dict) -> object:
    """抽取前端源码中的单个函数，在受控命名空间中编译执行并返回。"""
    fn, path = _extract_function(name)
    namespace = {"__builtins__": __builtins__, **extra_globals}
    # noqa: S102 — 执行的是本仓库前端抽取出的受控函数源码，非不可信输入
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"), namespace)  # noqa: S102
    return namespace[name]


def _jwt_with_payload(payload: dict) -> str:
    seg = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{seg}.signature"


# ── api_delete helper ────────────────────────────────────────────────────────


def test_api_delete_exists_and_retries_on_401():
    fn, path = _extract_function("api_delete")
    src = ast.get_source_segment(FRONTEND_SOURCES[path], fn)
    assert src is not None
    assert "requests.delete(" in src, "api_delete 必须发起 DELETE 请求"
    assert "r.status_code == 401 and _refresh_access_token()" in src, (
        "api_delete 必须在 401 时用 refresh token 重试（与 api_post/api_get 同模式）"
    )


# ── 角色解析（login 响应体不含 role，须从 JWT payload 解码）────────────────


def test_role_from_token_parses_admin_role():
    role_from_token = _exec_function("_role_from_token", {"base64": base64, "json": json})
    token = _jwt_with_payload({"sub": "u1", "role": "admin"})
    assert role_from_token(token) == "admin"


def test_role_from_token_returns_empty_for_malformed_token():
    role_from_token = _exec_function("_role_from_token", {"base64": base64, "json": json})
    assert role_from_token("not-a-jwt") == ""
    assert role_from_token("") == ""
    # payload 不是合法 base64/JSON 时也应安全回退
    assert role_from_token("a.@@@.c") == ""


# ── 删除入口的角色门控 ───────────────────────────────────────────────────────


def test_delete_button_only_rendered_for_admin():
    assert 'st.session_state.get("user_role") == "admin"' in SOURCE, (
        "删除按钮必须以 user_role == admin 为渲染前提（非 admin 调 DELETE 会 403）"
    )
    assert "can_delete=is_admin" in SOURCE, "组件删除按钮必须由 admin 状态控制渲染"
    assert 'session_event.get("action") == "delete"' in SOURCE


# ── 二次确认弹窗与当前会话重置 ───────────────────────────────────────────────


def test_confirm_dialog_contract():
    assert '@st.dialog("确认删除会话")' in SOURCE, "删除必须经过 st.dialog 二次确认"
    assert "级联清除" in SOURCE, "弹窗必须警示级联删除后果"
    assert "不可撤销" in SOURCE, "弹窗必须声明不可撤销"
    assert 'api_delete(f"/sessions/{session_id}")' in SOURCE


def test_current_session_delete_resets_state():
    assert "这是当前正在使用的会话" in SOURCE, "删除当前会话时弹窗必须给出专门提示"
    stub_state = SimpleNamespace()
    reset_fn = _exec_function(
        "_reset_session_state", {"st": SimpleNamespace(session_state=stub_state)}
    )
    reset_fn()
    assert stub_state.session_id is None
    assert stub_state.current_state == "init"
    assert stub_state.messages == []
    assert stub_state.pending_flags == []
    assert stub_state.pending_actions == []
    assert stub_state.interrupt_records == []
    assert stub_state.stage_readiness == {}
    assert stub_state.selected_scenario_id is None
    assert stub_state.reset_scenario_selector is True
