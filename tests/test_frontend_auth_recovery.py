"""认证刷新终态/瞬时失败分类的前端契约测试。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
AUTH_SOURCE = (FRONTEND_DIR / "models" / "auth.py").read_text(encoding="utf-8")
AUTH_TREE = ast.parse(AUTH_SOURCE)


def _load_refresh_function():
    fn = next(
        node
        for node in ast.walk(AUTH_TREE)
        if isinstance(node, ast.FunctionDef) and node.name == "_refresh_access_token"
    )
    return fn


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _State:
    """属性访问代理，直接读写底层 dict，便于断言函数副作用。"""

    def __init__(self, data: dict) -> None:
        object.__setattr__(self, "_data", data)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self._data[name] = value


def _refresh(state: dict, response: _Response | Exception):
    state_obj = _State(state)
    requests_module = SimpleNamespace(
        post=lambda *args, **kwargs: (
            (_ for _ in ()).throw(response) if isinstance(response, Exception) else response
        ),
        exceptions=SimpleNamespace(RequestException=Exception),
    )
    namespace = {
        "__builtins__": __builtins__,
        "st": SimpleNamespace(session_state=state_obj),
        "requests": requests_module,
        "API_BASE": "http://api",
        "_role_from_token": lambda token: "admin" if token else "",
    }
    fn = _load_refresh_function()
    exec(  # noqa: S102 — 执行本仓库前端抽取出的受控函数源码
        compile(ast.Module(body=[fn], type_ignores=[]), "auth.py", "exec"),
        namespace,
    )
    return namespace["_refresh_access_token"]()


def test_refresh_without_token_is_rejected():
    assert _refresh({"access_token": "old"}, _Response(200)) == "rejected"


def test_refresh_401_is_rejected():
    state = {"access_token": "old", "refresh_token": "refresh"}
    assert _refresh(state, _Response(401)) == "rejected"
    assert state["access_token"] == "old"  # noqa: S105 — 测试用假令牌


def test_refresh_server_error_and_network_error_are_transient():
    state = {"access_token": "old", "refresh_token": "refresh"}
    assert _refresh(state, _Response(503)) == "transient"
    assert _refresh(state, RuntimeError("boom")) == "transient"
    assert state["access_token"] == "old"  # noqa: S105 — 测试用假令牌


def test_refresh_success_updates_access_token_and_role():
    state = {"access_token": "old", "refresh_token": "refresh"}
    assert _refresh(state, _Response(200, {"access_token": "new-token"})) == "ok"
    assert state["access_token"] == "new-token"  # noqa: S105 — 测试用假令牌
    assert state["user_role"] == "admin"


def test_refresh_response_without_access_token_is_rejected():
    state = {"access_token": "old", "refresh_token": "refresh"}
    assert _refresh(state, _Response(200, {"detail": "invalid"})) == "rejected"
