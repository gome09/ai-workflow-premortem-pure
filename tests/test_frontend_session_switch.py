"""会话切换/刷新：失败保持当前会话，成功以服务端 ctx 为准。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

CONTROLLER = (
    Path(__file__).resolve().parent.parent / "frontend" / "controllers" / "session_controller.py"
)
SOURCE = CONTROLLER.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


class _Rerun(Exception):
    pass


class _State(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _state(**overrides):
    defaults = dict(
        session_id="A",
        current_state="s1_review",
        messages=[{"role": "user", "content": "A 的消息"}],
        pending_flags=[],
        pending_actions=[{"action_id": "ACT-A", "status": "pending"}],
        interrupt_records=[],
        stage_readiness={"stage_1": {"can_continue": False}},
        stage_resolution={},
        stage_advancement_decisions={},
        stage_advancement_decision=None,
        selected_scenario_id=None,
        session_load_error="",
        session_read_error="",
        actions_error="",
        readiness_error="",
    )
    defaults.update(overrides)
    return _State(defaults)


def _load(name: str):
    fn = next(
        node for node in ast.walk(TREE) if isinstance(node, ast.FunctionDef) and node.name == name
    )
    return fn


def _exec(name: str, namespace: dict):
    fn = _load(name)
    namespace = {"__builtins__": __builtins__, **namespace}
    exec(  # noqa: S102 — 执行本仓库前端抽取出的受控函数源码
        compile(ast.Module(body=[fn], type_ignores=[]), str(CONTROLLER), "exec"), namespace
    )
    return namespace[name]


def _select(state, *, get_session, actions=(True, []), readiness=(True, {}), interrupts=(True, [])):
    calls: list[str] = []

    def tracked_get(session_id):
        calls.append(session_id)
        return get_session(session_id)

    fn = _exec(
        "select_session",
        {
            "st": SimpleNamespace(
                session_state=state,
                rerun=lambda: (_ for _ in ()).throw(_Rerun()),
            ),
            "get_session_checked": tracked_get,
            "list_actions_checked": lambda *args, **kwargs: actions,
            "get_stage_readiness_checked": lambda *args, **kwargs: readiness,
            "list_interrupt_records_checked": lambda *args, **kwargs: interrupts,
            "clear_flash": lambda: None,
            "restore_messages_from_ctx": lambda ctx: [
                {"role": msg["role"], "content": msg["content"], "metadata": {}}
                for msg in ctx.get("conversation_history", {}).get("1", [])
            ],
        },
    )
    try:
        fn({"session_id": "B", "current_state": "stale-list-state"})
    except _Rerun:
        pass
    return calls


def test_switch_failure_keeps_current_session_and_messages():
    state = _state()
    calls = _select(state, get_session=lambda session_id: (False, None))

    assert calls == ["B"]
    assert state.session_id == "A"
    assert state.messages == [{"role": "user", "content": "A 的消息"}]
    assert state.pending_actions == [{"action_id": "ACT-A", "status": "pending"}]
    assert "无法加载会话 B" in state.session_load_error


def test_switch_success_uses_ctx_state_not_stale_list_state():
    state = _state()
    ctx = {
        "current_state": "s2_review",
        "selected_scenario_id": None,
        "conversation_history": {"1": [{"role": "user", "content": "B 的消息"}]},
        "flagged_items": [],
        "pending_actions": [],
    }
    _select(state, get_session=lambda session_id: (True, ctx))

    assert state.session_id == "B"
    assert state.current_state == "s2_review"
    assert state.messages == [{"role": "user", "content": "B 的消息", "metadata": {}}]
    assert state.session_load_error == ""


def test_same_session_click_refetches_ctx():
    state = _state(session_id="B")
    ctx = {
        "current_state": "s3_review",
        "selected_scenario_id": None,
        "conversation_history": {},
        "flagged_items": [],
        "pending_actions": [],
    }
    calls = _select(state, get_session=lambda session_id: (True, ctx))
    assert calls == ["B"], "同 ID 再次点击也必须重新拉取，便于失败重试/手动刷新"


def test_switch_readiness_failure_is_unknown_not_reused():
    state = _state()
    ctx = {
        "current_state": "s2_review",
        "selected_scenario_id": None,
        "conversation_history": {},
        "flagged_items": [],
        "pending_actions": [],
    }
    _select(state, get_session=lambda session_id: (True, ctx), readiness=(False, None))
    assert state.stage_readiness == {}
    assert "无法读取阶段门禁状态" in state.readiness_error
