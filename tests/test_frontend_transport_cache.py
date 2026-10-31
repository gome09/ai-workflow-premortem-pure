"""前端传输层缓存契约测试。

覆盖三件事：
  1) `_cached_get` 在 TTL 内复用结果、过期后重取、失败（None）不写缓存；
  2) `invalidate_api_cache` 能按前缀精确失效；
  3) api_client 复用共享连接池，且会话只读面板统一走缓存读取。
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_SOURCES = {
    path: path.read_text(encoding="utf-8") for path in sorted(FRONTEND_DIR.rglob("*.py"))
}
FRONTEND_TREES = {path: ast.parse(src) for path, src in FRONTEND_SOURCES.items()}
API_CLIENT_SOURCE = FRONTEND_SOURCES[FRONTEND_DIR / "models" / "api_client.py"]


def _extract_function(name: str) -> tuple[ast.FunctionDef, Path]:
    for path, tree in FRONTEND_TREES.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node, path
    raise AssertionError(f"frontend/**/*.py 中未找到函数 {name}")


def _exec_function(name: str, extra_globals: dict) -> object:
    fn, path = _extract_function(name)
    namespace = {"__builtins__": __builtins__, **extra_globals}
    # noqa: S102 — 执行的是本仓库前端抽取出的受控函数源码，非不可信输入
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"), namespace)  # noqa: S102
    return namespace[name]


def _cached_get_with(state: dict, api_get, clock: list[float]):
    return _exec_function(
        "_cached_get",
        {
            "st": SimpleNamespace(session_state=state),
            "time": SimpleNamespace(monotonic=lambda: clock[0]),
            "api_get": api_get,
            "_API_CACHE_KEY": "_api_cache",
        },
    )


def test_cached_get_reuses_value_within_ttl():
    calls: list[str] = []

    def fake_api_get(path: str) -> dict:
        calls.append(path)
        return {"call": len(calls)}

    state: dict = {}
    clock = [100.0]
    cached_get = _cached_get_with(state, fake_api_get, clock)

    first = cached_get("k", "/x", 5.0)
    second = cached_get("k", "/x", 5.0)

    assert calls == ["/x"], "TTL 内重复读取不应再请求后端"
    assert first == second
    assert state["_api_cache"]["k"][1] == first


def test_cached_get_refetches_after_ttl():
    calls: list[str] = []

    def fake_api_get(path: str) -> dict:
        calls.append(path)
        return {"call": len(calls)}

    state: dict = {}
    clock = [100.0]
    cached_get = _cached_get_with(state, fake_api_get, clock)

    cached_get("k", "/x", 5.0)
    clock[0] += 6.0
    refreshed = cached_get("k", "/x", 5.0)

    assert calls == ["/x", "/x"], "超过 TTL 后必须回源"
    assert refreshed == {"call": 2}


def test_cached_get_does_not_cache_failures():
    calls: list[str] = []

    def failing_api_get(path: str) -> None:
        calls.append(path)
        return None

    state: dict = {}
    clock = [100.0]
    cached_get = _cached_get_with(state, failing_api_get, clock)

    assert cached_get("k", "/x", 5.0) is None
    assert cached_get("k", "/x", 5.0) is None

    assert calls == ["/x", "/x"], "失败结果不得缓存，否则错误会被静默保留"
    assert state["_api_cache"] == {}


def test_invalidate_api_cache_by_prefix_and_all():
    state: dict = {
        "_api_cache": {
            "session:s1:evidence": (0.0, []),
            "session:s2:evidence": (0.0, []),
            "sessions:list": (0.0, []),
        }
    }
    invalidate = _exec_function(
        "invalidate_api_cache",
        {"st": SimpleNamespace(session_state=state), "_API_CACHE_KEY": "_api_cache"},
    )

    invalidate("session:s1:")
    assert sorted(state["_api_cache"]) == ["session:s2:evidence", "sessions:list"]

    invalidate()
    assert state["_api_cache"] == {}


def test_api_client_uses_shared_pooled_session():
    assert "_http_session.mount(" in API_CLIENT_SOURCE, "必须挂载连接池适配器"
    assert "pool_maxsize=20" in API_CLIENT_SOURCE, "连接池上限需显式配置"
    assert "r = _http_session.get(" in API_CLIENT_SOURCE
    assert "r = _http_session.post(" in API_CLIENT_SOURCE


def test_session_panel_reads_go_through_cache():
    for name in (
        "list_evidence",
        "list_safety_findings",
        "list_audit_events",
        "list_report_artifacts",
        "list_eval_cases",
        "list_eval_runs",
        "list_redteam_cases",
    ):
        fn, path = _extract_function(name)
        src = ast.get_source_segment(FRONTEND_SOURCES[path], fn)
        assert src is not None
        assert "_cached_get(" in src, f"{name} 必须走会话级缓存读取"
        assert "_session_cache_key(" in src, f"{name} 的缓存键必须按会话隔离"
