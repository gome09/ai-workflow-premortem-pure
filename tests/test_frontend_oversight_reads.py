"""人工监督/门禁读取失败时不得显示为零事项或零阻断。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
SESSION_STATE_SOURCE = (FRONTEND / "models" / "session_state.py").read_text(encoding="utf-8")
GOVERNANCE_SOURCE = (FRONTEND / "views" / "panels" / "governance_panels.py").read_text(
    encoding="utf-8"
)
LIVE_SOURCE = (FRONTEND / "views" / "live_oversight.py").read_text(encoding="utf-8")
GATE_SOURCE = (FRONTEND / "views" / "panels" / "gate_panel.py").read_text(encoding="utf-8")


class _State(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _Recorder:
    def __init__(self) -> None:
        self.successes: list[str] = []
        self.warnings: list[str] = []
        self.subheaders: list[str] = []

    def success(self, message: str, *args, **kwargs) -> None:
        self.successes.append(message)

    def warning(self, message: str, *args, **kwargs) -> None:
        self.warnings.append(message)

    def subheader(self, message: str, *args, **kwargs) -> None:
        self.subheaders.append(message)

    def caption(self, *args, **kwargs) -> None:
        return None

    def markdown(self, *args, **kwargs) -> None:
        return None

    def expander(self, *args, **kwargs):
        raise AssertionError("空状态测试不应展开动作/阻断详情")


def _exec(source: str, name: str, namespace: dict, filename: str):
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {"__builtins__": __builtins__, **namespace}
    exec(  # noqa: S102 — 执行本仓库前端抽取出的受控函数源码
        compile(ast.Module(body=[fn], type_ignores=[]), filename, "exec"),
        namespace,
    )
    return namespace[name]


def _state(**overrides) -> _State:
    state = _State(
        session_id="s1",
        pending_actions=[],
        stage_readiness={"stage_1": {"can_continue": False}},
        interrupt_records=[],
        actions_error="",
        readiness_error="",
        stage_advancement_decisions={},
        stage_advancement_decision=None,
    )
    state.update(overrides)
    return state


def _refresh_actions(state, actions, readiness):
    fn = _exec(
        SESSION_STATE_SOURCE,
        "refresh_actions",
        {
            "st": SimpleNamespace(session_state=state),
            "invalidate_session_cache": lambda session_id: None,
            "list_actions_checked": lambda *args, **kwargs: actions,
            "get_stage_readiness_checked": lambda *args, **kwargs: readiness,
            "list_interrupt_records_checked": lambda *args, **kwargs: (True, []),
        },
        "session_state.py",
    )
    fn()


def test_actions_failure_preserves_previous_and_marks_unknown():
    old_actions = [{"action_id": "ACT-1"}]
    state = _state(pending_actions=old_actions)
    _refresh_actions(state, actions=(False, None), readiness=(True, {"stage_1": {}}))

    assert state.pending_actions == old_actions
    assert "无法读取待处理人工动作" in state.actions_error
    assert state.readiness_error == ""
    assert state.stage_readiness == {"stage_1": {}}


def test_readiness_failure_preserves_previous_and_marks_unknown():
    old_readiness = {"stage_1": {"can_continue": False}}
    state = _state(stage_readiness=old_readiness)
    _refresh_actions(state, actions=(True, []), readiness=(False, None))

    assert state.stage_readiness == old_readiness
    assert "无法读取阶段门禁状态" in state.readiness_error
    assert state.actions_error == ""


def test_success_empty_clears_errors_and_shows_zero_state():
    state = _state(
        actions_error="上一次失败",
        readiness_error="上一次失败",
    )
    _refresh_actions(state, actions=(True, []), readiness=(True, {}))

    assert state.pending_actions == []
    assert state.actions_error == ""
    assert state.readiness_error == ""


def test_action_queue_does_not_claim_zero_actions_on_read_failure():
    recorder = _Recorder()
    state = _state(actions_error="无法读取待处理人工动作，当前显示可能不是最新结果。")
    st = SimpleNamespace(
        session_state=state,
        warning=recorder.warning,
        subheader=recorder.subheader,
        caption=recorder.caption,
        expander=recorder.expander,
    )
    fn = _exec(
        GOVERNANCE_SOURCE,
        "render_action_queue",
        {"st": st},
        "governance_panels.py",
    )
    fn()

    assert any("无法读取待处理人工动作" in message for message in recorder.warnings)
    assert not any("无待处理人工动作" in message for message in recorder.subheaders)


def test_live_oversight_does_not_claim_no_items_on_read_failure():
    recorder = _Recorder()
    state = _state(actions_error="待处理动作读取失败", readiness_error="门禁读取失败")
    st = SimpleNamespace(
        session_state=state,
        success=recorder.success,
        warning=recorder.warning,
        markdown=recorder.markdown,
        caption=recorder.caption,
    )
    fn = _exec(
        LIVE_SOURCE,
        "render_live_oversight",
        {
            "st": st,
            "_pending_actions_for_stage": lambda stage_id: [],
            "_blockers_for_stage": lambda stage_id: [],
        },
        "live_oversight.py",
    )
    fn(1)

    assert not recorder.successes
    assert any("暂不可用" in message for message in recorder.warnings)


def test_advancement_failure_is_not_treated_as_zero_blockers():
    state = _state()
    st = SimpleNamespace(session_state=state)
    fn = _exec(
        GATE_SOURCE,
        "_stage_advancement_decision",
        {
            "st": st,
            "get_stage_advancement_decision_checked": lambda *args, **kwargs: (False, None),
        },
        "gate_panel.py",
    )

    assert fn(1) == {}
    assert "无法读取阶段推进判定" in state.advancement_error
    assert "gate_unknown" in GATE_SOURCE
    assert "当前阶段没有阻断项" in GATE_SOURCE
