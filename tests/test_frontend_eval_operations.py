"""评测实验：请求键复用、状态失败上限与终态反馈的前端契约。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

CONTROLLER = (
    Path(__file__).resolve().parent.parent / "frontend" / "controllers" / "eval_controller.py"
)
PANEL = Path(__file__).resolve().parent.parent / "frontend" / "views" / "panels" / "eval_panels.py"
CONTROLLER_SOURCE = CONTROLLER.read_text(encoding="utf-8")
PANEL_SOURCE = PANEL.read_text(encoding="utf-8")


class _State(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _Rerun(Exception):
    pass


class _Spinner:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


class _Recorder:
    def __init__(self) -> None:
        self.successes: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.captions: list[str] = []
        self.infos: list[str] = []

    def success(self, message, *args, **kwargs):
        self.successes.append(message)

    def warning(self, message, *args, **kwargs):
        self.warnings.append(message)

    def error(self, message, *args, **kwargs):
        self.errors.append(message)

    def caption(self, message, *args, **kwargs):
        self.captions.append(message)

    def info(self, message, *args, **kwargs):
        self.infos.append(message)

    def spinner(self, *args, **kwargs):
        return SimpleNamespace(__enter__=lambda self: None, __exit__=lambda *a: False)


def _exec_functions(source: str, names: tuple[str, ...], namespace: dict, filename: str):
    tree = ast.parse(source)
    functions = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {"__builtins__": __builtins__, **namespace}
    exec(  # noqa: S102 — 执行本仓库前端抽取出的受控函数源码
        compile(ast.Module(body=functions, type_ignores=[]), filename, "exec"),
        namespace,
    )
    return namespace


def _base_state(**overrides) -> _State:
    state = _State(
        session_id="s1",
        eval_run_keys={},
        eval_run_modes={},
        eval_experiment_status={},
        eval_status_failures={},
    )
    state.update(overrides)
    return state


def test_request_key_is_stable_across_retries():
    state = _base_state()
    ns = _exec_functions(
        CONTROLLER_SOURCE,
        ("_request_key",),
        {"st": SimpleNamespace(session_state=state), "uuid": __import__("uuid")},
        "eval_controller.py",
    )
    first = ns["_request_key"]("EXP-1")
    second = ns["_request_key"]("EXP-1")
    assert first == second
    assert first.startswith("ui:EXP-1:")


def test_status_failures_stop_after_limit_without_success():
    state = _base_state()
    recorder = _Recorder()
    ns = _exec_functions(
        CONTROLLER_SOURCE,
        ("_status_store", "_remember_status", "refresh_experiment_status"),
        {
            "st": SimpleNamespace(session_state=state),
            "get_eval_experiment_status_checked": lambda *args, **kwargs: (False, None),
        },
        "eval_controller.py",
    )
    for _ in range(5):
        assert ns["refresh_experiment_status"]("EXP-1") is None
    stored = state["eval_experiment_status"]["EXP-1"]
    assert "状态读取连续失败" in stored["status_error"]
    assert not recorder.successes


def test_terminal_render_never_claims_success():
    state = _base_state(
        eval_experiment_status={
            "EXP-1": {
                "status": "failed",
                "execution_mode": "target_http",
                "last_error_code": "experiment_timeout",
                "completed_cases": 1,
                "total_cases": 3,
                "failed_cases": 1,
            }
        }
    )
    recorder = _Recorder()
    ns = _exec_functions(
        PANEL_SOURCE,
        ("_experiment_tracked_status", "_render_experiment_status"),
        {"st": SimpleNamespace(session_state=state, **recorder.__dict__)},
        "eval_panels.py",
    )
    # 用显式绑定替换 SimpleNamespace 的属性捕获
    ns["_render_experiment_status"].__globals__["st"] = SimpleNamespace(
        session_state=state,
        warning=recorder.warning,
        error=recorder.error,
        caption=recorder.caption,
        info=recorder.info,
        success=recorder.success,
    )
    ns["_render_experiment_status"]("EXP-1")

    assert not recorder.successes
    assert any("未完成" in message for message in recorder.errors)


def test_run_experiment_posts_once_and_reuses_key():
    state = _base_state()
    calls: list[str] = []

    def fake_run(session_id, experiment_id, **kwargs):
        calls.append(kwargs["idempotency_key"])
        return {"accepted": True}

    ns = _exec_functions(
        CONTROLLER_SOURCE,
        ("_status_store", "_request_key", "_remember_status", "run_experiment"),
        {
            "st": SimpleNamespace(
                session_state=state,
                spinner=lambda *a, **k: _Spinner(),
                rerun=lambda: (_ for _ in ()).throw(_Rerun()),
            ),
            "run_eval_experiment": fake_run,
            "invalidate_session_cache": lambda session_id: None,
            "uuid": __import__("uuid"),
        },
        "eval_controller.py",
    )
    for _ in range(2):
        try:
            ns["run_experiment"]("EXP-1", dry_run_only=False, run_mode="target_http")
        except _Rerun:
            pass

    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert state["eval_experiment_status"]["EXP-1"]["status"] == "accepted"


def test_no_long_synchronous_polling_remains():
    assert "range(900)" not in CONTROLLER_SOURCE
    assert "time.sleep(2)" not in CONTROLLER_SOURCE
    poll_start = PANEL_SOURCE.index("def _poll_experiment_status")
    poll_end = PANEL_SOURCE.index("def render_redteam_section")
    poll_source = PANEL_SOURCE[poll_start:poll_end]
    assert "refresh_experiment_status(" in poll_source
    assert "run_experiment(" not in poll_source, "轮询只能 GET，不能自动提交/恢复"
