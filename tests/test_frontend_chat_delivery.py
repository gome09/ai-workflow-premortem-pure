# tests/test_frontend_chat_delivery.py
"""聊天消息投递状态：明确拒绝 vs 结果未知，草稿与一次性反馈。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
CONTROLLER_PATH = FRONTEND_DIR / "controllers" / "session_controller.py"
FEEDBACK_PATH = FRONTEND_DIR / "models" / "feedback.py"
CONTROLLER_SOURCE = CONTROLLER_PATH.read_text(encoding="utf-8")
FEEDBACK_SOURCE = FEEDBACK_PATH.read_text(encoding="utf-8")
SINGLE_WORKBENCH_SOURCE = (FRONTEND_DIR / "views" / "workbench.py").read_text(encoding="utf-8")


class _State(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _Spinner:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


def _exec(source: str, names: tuple[str, ...], extra: dict, filename: str) -> dict:
    tree = ast.parse(source)
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            nodes.append(node)
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in names
        ):
            nodes.append(node)
    namespace = {"__builtins__": __builtins__, **extra}
    exec(  # noqa: S102 — 执行本仓库前端抽取出的受控源码
        compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"),
        namespace,
    )
    return namespace


_FEEDBACK_NS: dict | None = None


def _feedback_ns() -> dict:
    global _FEEDBACK_NS
    if _FEEDBACK_NS is None:
        _FEEDBACK_NS = _exec(
            FEEDBACK_SOURCE,
            ("ApiError", "_detail_text", "_describe_http_error", "describe_api_error"),
            {},
            "feedback.py",
        )
    return _FEEDBACK_NS


def _api_error_class() -> type:
    return _feedback_ns()["ApiError"]


def _describe(name: str):  # noqa: ANN202
    return _feedback_ns()[name]


def _handle_send(send_message, state: _State):
    ApiError = _api_error_class()
    describe_api_error = _describe("describe_api_error")

    def set_flash(level: str, message: str) -> None:
        state["_flash"] = {"level": level, "message": message}

    def clear_flash() -> None:
        state.pop("_flash", None)

    def show_api_error(exc, *, fallback: str = "") -> None:
        state.setdefault("_errors", []).append(describe_api_error(exc) or fallback)

    ns = _exec(
        CONTROLLER_SOURCE,
        ("_UNKNOWN_OUTCOME_KINDS", "_outcome_is_unknown", "_mark_delivery_failure", "handle_send"),
        {
            "st": SimpleNamespace(
                session_state=state,
                spinner=lambda *args, **kwargs: _Spinner(),
            ),
            "ApiError": ApiError,
            "describe_api_error": describe_api_error,
            "set_flash": set_flash,
            "clear_flash": clear_flash,
            "show_api_error": show_api_error,
            "send_message": send_message,
            "refresh_flags": lambda: None,
            "refresh_actions": lambda: None,
        },
        "session_controller.py",
    )
    return ns["handle_send"]


def _state() -> _State:
    return _State(session_id="s1", messages=[], current_state="s1_review")


def test_success_marks_confirmed_and_appends_reply():
    state = _state()
    handle_send = _handle_send(
        lambda **kwargs: {"ai_reply": "好的", "current_state": "s1_review"},
        state,
    )

    handle_send("继续")

    assert [msg["role"] for msg in state["messages"]] == ["user", "assistant"]
    assert state["messages"][0]["metadata"]["delivery_status"] == "confirmed"
    assert state["messages"][1]["content"] == "好的"
    assert state["current_state"] == "s1_review"
    assert "chat_retry_draft" not in state
    assert "_flash" not in state


def test_forbidden_rejection_marks_failed_and_keeps_retry_draft():
    state = _state()
    ApiError = _api_error_class()

    def reject(**kwargs):
        raise ApiError("http", status_code=403, detail={"error_message": "仅 editor 可发言"})

    handle_send = _handle_send(reject, state)
    handle_send("这条会被拒绝")

    assert len(state["messages"]) == 1
    message = state["messages"][0]
    assert message["metadata"]["delivery_status"] == "failed"
    assert "仅 editor 可发言" in message["metadata"]["delivery_error"]
    assert state["chat_retry_draft"] == "这条会被拒绝"
    assert state["_flash"]["level"] == "error"
    assert "消息未发送" in state["_flash"]["message"]


def test_validation_error_is_failed_not_unknown():
    state = _state()
    ApiError = _api_error_class()

    def reject(**kwargs):
        raise ApiError(
            "http",
            status_code=422,
            detail=[{"loc": ["body", "user_input"], "msg": "too long"}],
        )

    handle_send = _handle_send(reject, state)
    handle_send("x" * 10)

    assert state["messages"][0]["metadata"]["delivery_status"] == "failed"
    assert "too long" in state["messages"][0]["metadata"]["delivery_error"]


def test_timeout_marks_unknown_without_retry_draft():
    state = _state()
    ApiError = _api_error_class()

    def timeout(**kwargs):
        raise ApiError("timeout")

    handle_send = _handle_send(timeout, state)
    handle_send("结果未知的消息")

    assert len(state["messages"]) == 1
    assert state["messages"][0]["metadata"]["delivery_status"] == "unknown"
    assert state["messages"][0]["metadata"].get("delivery_error") is None
    assert "chat_retry_draft" not in state
    assert state["_flash"]["level"] == "warning"
    assert "不会自动重发" in state["_flash"]["message"]


def test_server_error_is_unknown():
    state = _state()
    ApiError = _api_error_class()

    def fail(**kwargs):
        raise ApiError("http", status_code=503)

    handle_send = _handle_send(fail, state)
    handle_send("可能已处理")

    assert state["messages"][0]["metadata"]["delivery_status"] == "unknown"
    assert "chat_retry_draft" not in state


def test_workbench_renders_delivery_markers_and_retry_area():
    assert "⏳ 结果未知：请刷新核对" in SINGLE_WORKBENCH_SOURCE
    assert "⚠️ 未发送" in SINGLE_WORKBENCH_SOURCE
    assert 'key="chat_retry_edit"' in SINGLE_WORKBENCH_SOURCE
    assert 'key="chat_retry_send"' in SINGLE_WORKBENCH_SOURCE
    assert "render_flash()" in SINGLE_WORKBENCH_SOURCE
