# tests/test_frontend_api_errors.py
"""前端 ApiError 契约：结构化错误解析与可行动中文提示。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FEEDBACK_PATH = FRONTEND_DIR / "models" / "feedback.py"
API_CLIENT_PATH = FRONTEND_DIR / "models" / "api_client.py"
FEEDBACK_SOURCE = FEEDBACK_PATH.read_text(encoding="utf-8")
API_CLIENT_SOURCE = API_CLIENT_PATH.read_text(encoding="utf-8")


def _exec_nodes(source: str, filename: str, names: tuple[str, ...], extra: dict) -> dict:
    tree = ast.parse(source)
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names
    ]
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
        _FEEDBACK_NS = _exec_nodes(
            FEEDBACK_SOURCE,
            "feedback.py",
            ("ApiError", "_detail_text", "_describe_http_error", "describe_api_error"),
            {"st": SimpleNamespace(session_state={})},
        )
    return _FEEDBACK_NS


class _Timeout(Exception):
    pass


class _ConnectionError(Exception):
    pass


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


def _api_client_ns(*, session=None) -> dict:
    requests = SimpleNamespace(
        exceptions=SimpleNamespace(Timeout=_Timeout, ConnectionError=_ConnectionError)
    )
    return {
        "dataclass": __import__("dataclasses").dataclass,
        "requests": requests,
        "st": SimpleNamespace(session_state=session or {}, rerun=lambda: None),
        "API_BASE": "http://api",
        "_auth_headers": lambda: {},
        "_refresh_access_token": lambda: "ok",
        "_expire_login_state": lambda: None,
        "_http_session": SimpleNamespace(),
    }


def _perform_with(response=None, *, error: Exception | None = None):  # noqa: ANN202
    ns = _api_client_ns()

    def fake_send(url, **kwargs):
        if error is not None:
            raise error
        return response if response is not None else _Response(200, {})

    ns["_http_session"] = SimpleNamespace(
        **{method: fake_send for method in ("get", "post", "patch", "put", "delete")}
    )
    ns = _exec_nodes(
        API_CLIENT_SOURCE,
        "api_client.py",
        ("_HttpOutcome", "_perform"),
        ns,
    )
    perform = ns["_perform"]

    def call(method: str = "post"):  # noqa: ANN202
        return perform(method, "/x", timeout=1)

    return call


# ── describe_api_error ──────────────────────────────────────────────────────


def _err(kind: str, **kwargs):
    ns = _feedback_ns()
    return ns["ApiError"](kind, **kwargs)


def test_timeout_result_unknown_message():
    ns = _feedback_ns()
    message = ns["describe_api_error"](_err("timeout"))
    assert "结果可能未确定" in message
    assert "不要自动重复提交" in message


def test_connection_message():
    ns = _feedback_ns()
    assert "无法连接后端服务" in ns["describe_api_error"](_err("connection"))


def test_forbidden_prefers_backend_detail():
    ns = _feedback_ns()
    message = ns["describe_api_error"](
        _err("http", status_code=403, detail={"error_message": "仅 admin 可批准"})
    )
    assert message == "仅 admin 可批准"
    fallback = ns["describe_api_error"](_err("http", status_code=403))
    assert "无权" in fallback


def test_not_found_and_stale_conflict_messages():
    ns = _feedback_ns()
    assert "不存在" in ns["describe_api_error"](_err("http", status_code=404))
    stale = ns["describe_api_error"](
        _err("http", status_code=409, detail={"result_status": "stale"})
    )
    assert "刷新后重试" in stale
    blocked = ns["describe_api_error"](
        _err(
            "http",
            status_code=409,
            detail="Workflow state does not allow advancement",
            recovery_endpoint="/sessions/s1/workflow/recover",
        )
    )
    assert "可使用恢复入口" in blocked


def test_validation_error_list_and_dict():
    ns = _feedback_ns()
    listed = ns["describe_api_error"](
        _err(
            "http",
            status_code=422,
            detail=[
                {"loc": ["body", "name"], "msg": "field required"},
                {"loc": ["body", "endpoint"], "msg": "invalid url"},
            ],
        )
    )
    assert "name: field required" in listed
    assert "endpoint: invalid url" in listed
    as_dict = ns["describe_api_error"](
        _err("http", status_code=422, detail={"error_message": "用例版本已变化"})
    )
    assert "用例版本已变化" in as_dict


def test_model_provider_502_reports_retryability_without_raw_detail():
    ns = _feedback_ns()
    retryable = ns["describe_api_error"](
        _err(
            "http",
            status_code=502,
            detail="provider raw body",
            error_code="rate_limit",
            retryable=True,
        )
    )
    assert "rate_limit" in retryable and "可重试" in retryable
    assert "provider raw body" not in retryable

    fatal = ns["describe_api_error"](
        _err("http", status_code=502, error_code="auth", retryable=False)
    )
    assert "不可重试" in fatal


def test_server_error_and_invalid_response():
    ns = _feedback_ns()
    assert "HTTP 503" in ns["describe_api_error"](_err("http", status_code=503))
    assert "无法识别" in ns["describe_api_error"](_err("invalid_response", status_code=200))


def test_non_api_error_is_left_to_caller_fallback():
    ns = _feedback_ns()
    assert ns["describe_api_error"](RuntimeError("boom")) == ""


# ── _perform structured parsing ─────────────────────────────────────────────


def test_perform_extracts_structured_error_fields():
    response = _Response(
        409,
        {
            "detail": {"result_status": "conflict", "error_message": "版本冲突"},
            "recovery_endpoint": "/sessions/s1/workflow/recover",
            "error_code": "conflict",
            "retryable": False,
        },
    )
    call = _perform_with(response)
    outcome = call()

    assert outcome.ok is False
    assert outcome.status_code == 409
    assert outcome.detail == {"result_status": "conflict", "error_message": "版本冲突"}
    assert outcome.error_code == "conflict"
    assert outcome.retryable is False
    assert outcome.recovery_endpoint == "/sessions/s1/workflow/recover"


def test_perform_extracts_top_level_llm_error_contract():
    response = _Response(
        502,
        {
            "detail": "Model provider call failed.",
            "error_code": "timeout",
            "retryable": True,
        },
    )
    outcome = _perform_with(response)()

    assert outcome.error_code == "timeout"
    assert outcome.retryable is True


def test_perform_classifies_timeout_and_no_content():
    outcome = _perform_with(error=_Timeout())()
    assert outcome.error_kind == "timeout"

    no_content = _perform_with(_Response(204, None))("delete")
    assert no_content.ok is True
    assert no_content.payload == {}


def test_request_raises_api_error_and_allows_404():
    ns = _api_client_ns()
    ns = _exec_nodes(
        API_CLIENT_SOURCE,
        "api_client.py",
        ("_HttpOutcome", "_request"),
        ns,
    )
    request = ns["_request"]
    ApiError = _feedback_ns()["ApiError"]
    request.__globals__["ApiError"] = ApiError

    request.__globals__["_perform"] = lambda *args, **kwargs: ns["_HttpOutcome"](
        False,
        status_code=403,
        error_kind="http",
        detail={"error_message": "仅 admin 可操作"},
    )
    with pytest.raises(ApiError) as excinfo:
        request("post", "/x")
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == {"error_message": "仅 admin 可操作"}

    request.__globals__["_perform"] = lambda *args, **kwargs: ns["_HttpOutcome"](
        False, status_code=404, error_kind="not_found"
    )
    assert request("get", "/x", allow_404=True) is None


def test_api_client_has_no_ui_feedback_in_transport_layer():
    for name in (
        "api_post",
        "api_get",
        "api_patch",
        "api_put",
        "api_delete",
        "_request",
        "_perform",
    ):
        fn = next(
            node
            for node in ast.walk(ast.parse(API_CLIENT_SOURCE))
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        src = ast.get_source_segment(API_CLIENT_SOURCE, fn) or ""
        assert "st.error(" not in src, f"{name} 不得直接渲染错误，提示由 controller/view 单点负责"
