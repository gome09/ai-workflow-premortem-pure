# tests/test_frontend_redteam_generation.py
"""红队生成：失败不得显示"已生成 0 条"，合法零条仍是成功。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
CONTROLLER_PATH = FRONTEND_DIR / "controllers" / "eval_controller.py"
FEEDBACK_PATH = FRONTEND_DIR / "models" / "feedback.py"
CONTROLLER_SOURCE = CONTROLLER_PATH.read_text(encoding="utf-8")
FEEDBACK_SOURCE = FEEDBACK_PATH.read_text(encoding="utf-8")


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


class _Recorder:
    def __init__(self) -> None:
        self.successes: list[str] = []
        self.errors: list[str] = []
        self.refreshes = 0

    def success(self, message, *args, **kwargs):
        self.successes.append(message)

    def error(self, message, *args, **kwargs):
        self.errors.append(message)


def _exec_functions(names: tuple[str, ...], extra: dict) -> dict:
    tree = ast.parse(CONTROLLER_SOURCE)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"__builtins__": __builtins__, **extra}
    exec(  # noqa: S102 — 执行本仓库前端抽取出的受控源码
        compile(ast.Module(body=nodes, type_ignores=[]), "eval_controller.py", "exec"),
        namespace,
    )
    return namespace


_FEEDBACK_NS: dict | None = None


def _feedback_ns() -> dict:
    global _FEEDBACK_NS
    if _FEEDBACK_NS is None:
        feedback_tree = ast.parse(FEEDBACK_SOURCE)
        feedback_nodes = [
            node
            for node in feedback_tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef))
            and node.name
            in ("ApiError", "_detail_text", "_describe_http_error", "describe_api_error")
        ]
        namespace = {"__builtins__": __builtins__}
        exec(  # noqa: S102
            compile(ast.Module(body=feedback_nodes, type_ignores=[]), "feedback.py", "exec"),
            namespace,
        )
        _FEEDBACK_NS = namespace
    return _FEEDBACK_NS


def _generate(generate_redteam_cases):
    feedback_ns = _feedback_ns()
    ApiError = feedback_ns["ApiError"]

    state = _State(session_id="s1")
    recorder = _Recorder()

    def show_api_error(exc, *, fallback: str = "") -> None:
        recorder.error(feedback_ns["describe_api_error"](exc) or fallback)

    def refresh_actions() -> None:
        recorder.refreshes += 1

    ns = _exec_functions(
        ("generate_redteam",),
        {
            "st": SimpleNamespace(
                session_state=state,
                success=recorder.success,
                error=recorder.error,
                rerun=lambda: (_ for _ in ()).throw(_Rerun()),
            ),
            "ApiError": ApiError,
            "show_api_error": show_api_error,
            "generate_redteam_cases": generate_redteam_cases,
            "refresh_actions": refresh_actions,
        },
    )
    return ns["generate_redteam"], recorder


def _run(fn):
    try:
        fn()
    except _Rerun:
        return True
    return False


def test_api_error_shows_no_success_and_no_rerun():
    ApiError = _error_class()

    def fail(session_id=None, **kwargs):
        raise ApiError("http", status_code=400, detail="stage 3 not ready")

    generate, recorder = _generate(fail)
    reran = _run(generate)

    assert reran is False
    assert recorder.successes == []
    assert recorder.errors == ["stage 3 not ready"]
    assert recorder.refreshes == 0


def test_server_error_shows_no_success():
    ApiError = _error_class()

    def fail(session_id=None, **kwargs):
        raise ApiError("http", status_code=500)

    generate, recorder = _generate(fail)
    assert _run(generate) is False
    assert recorder.successes == []
    assert any("HTTP 500" in message for message in recorder.errors)


def test_legal_empty_result_is_still_success():
    generate, recorder = _generate(lambda session_id=None, **kwargs: [])
    assert _run(generate) is True
    assert recorder.successes == ["已生成 0 条红队用例草稿。"]
    assert recorder.errors == []


def test_created_cases_report_actual_count():
    cases = [{"redteam_case_id": f"RT-{index}"} for index in range(3)]
    generate, recorder = _generate(lambda session_id=None, **kwargs: cases)
    assert _run(generate) is True
    assert recorder.successes == ["已生成 3 条红队用例草稿。"]


def _error_class() -> type:
    return _feedback_ns()["ApiError"]
