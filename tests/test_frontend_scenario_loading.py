"""会话工作台内置场景加载与空白新建的前端契约测试。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

APP_PATH = Path(__file__).resolve().parent.parent / "frontend" / "app.py"
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _extract_function(name: str) -> ast.FunctionDef:
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"frontend/app.py 中未找到函数 {name}")


def _exec_function(name: str, extra_globals: dict) -> object:
    fn = _extract_function(name)
    namespace = {"__builtins__": __builtins__, **extra_globals}
    # noqa: S102 — 执行仓库内已解析的受控函数，而非外部输入。
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(APP_PATH), "exec"), namespace)  # noqa: S102
    return namespace[name]


def test_activate_blank_session_clears_previous_scenario_and_messages():
    state = SimpleNamespace(
        selected_scenario_id="generic_rag_demo",
        messages=[{"role": "user", "content": "old"}],
    )
    activate = _exec_function(
        "_activate_created_session", {"st": SimpleNamespace(session_state=state)}
    )

    activate({"session_id": "blank-1", "current_state": "init", "selected_scenario_id": None})

    assert state.session_id == "blank-1"
    assert state.selected_scenario_id is None
    assert state.messages == []
    assert state.current_state == "init"
    assert state.pending_actions == []
    assert state.stage_readiness == {}


def test_bootstrap_exchange_uses_normal_chat_message_shape():
    state = SimpleNamespace()
    append_exchange = _exec_function(
        "_append_bootstrap_exchange", {"st": SimpleNamespace(session_state=state)}
    )

    append_exchange("scenario input", {"ai_reply": "scenario reply", "current_state": "s1_running"})

    assert state.messages == [
        {"role": "user", "content": "scenario input", "metadata": {}},
        {"role": "assistant", "content": "scenario reply", "metadata": {}},
    ]
    assert state.current_state == "s1_running"


def test_sidebar_scenario_and_blank_session_contracts_are_separate():
    assert '"➕ 新建空白会话", use_container_width=True' in SOURCE
    assert "created = create_session()" in SOURCE
    assert "created = create_session(selected_scenario_id)" in SOURCE
    assert 'bootstrap_scenario_input(created["session_id"], scenario_input)' in SOURCE
    assert 'scenario_placeholder = "选择内置场景"' in SOURCE
    assert "index=None" in SOURCE
    assert "placeholder=scenario_placeholder" in SOURCE
    assert "accept_new_options=False" in SOURCE
    assert "filter_mode=None" in SOURCE
    assert '"[选择内置场景]"' not in SOURCE
    assert 'scenario_options[item.get("name", "未命名场景")]' in SOURCE
    assert '"你好，我想开始一个新的项目分析。"' not in SOURCE


def test_sidebar_controls_use_requested_alignment_and_width():
    assert 'st.columns([3, 2], vertical_alignment="bottom")' in SOURCE
    assert 'st.markdown("**内置场景**")' not in SOURCE
    assert "with col_scenario:" in SOURCE
    assert "with col_refresh:" in SOURCE
    assert 'key="create_blank_session"' in SOURCE
    assert ".st-key-create_blank_session button p" in SOURCE
    assert "white-space: nowrap" in SOURCE
