"""侧栏会话列表搜索/分页与评测面板懒加载的前端契约测试。"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIDEBAR_PATH = ROOT / "frontend" / "views" / "sidebar.py"
API_CLIENT_PATH = ROOT / "frontend" / "models" / "api_client.py"
SIDEBAR_SOURCE = SIDEBAR_PATH.read_text(encoding="utf-8")
EVAL_SOURCE = (ROOT / "frontend" / "views" / "panels" / "eval_panels.py").read_text(
    encoding="utf-8"
)
API_CLIENT_SOURCE = API_CLIENT_PATH.read_text(encoding="utf-8")


def _exec_function(source: str, name: str, namespace: dict, filename: str):
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {"__builtins__": __builtins__, **namespace}
    exec(  # noqa: S102 — 执行本仓库前端抽取出的受控函数源码
        compile(ast.Module(body=[fn], type_ignores=[]), filename, "exec"), namespace
    )
    return namespace[name]


def test_session_list_supports_local_search():
    assert 'key="session_filter"' in SIDEBAR_SOURCE
    assert "_SESSION_SEARCH_FIELDS" in SIDEBAR_SOURCE
    assert "visible_sessions" in SIDEBAR_SOURCE


def test_session_list_requests_real_pages():
    assert "_SESSION_PAGE_SIZE = 20" in SIDEBAR_SOURCE
    assert "list_sessions_checked(" in SIDEBAR_SOURCE
    assert "session_extra_pages" in SIDEBAR_SOURCE
    assert "显示更多（+20）" in SIDEBAR_SOURCE
    assert "sessions[:10]" not in SIDEBAR_SOURCE
    assert "session_list_limit" not in SIDEBAR_SOURCE


def test_list_sessions_builds_limit_offset_and_cache_key():
    calls: list[tuple[str, str, float]] = []

    def fake_cached(cache_key, path, ttl):
        calls.append((cache_key, path, ttl))
        return True, []

    fn = _exec_function(
        API_CLIENT_SOURCE,
        "list_sessions_checked",
        {"_cached_get_checked": fake_cached, "_SESSION_LIST_TTL": 10.0},
        "api_client.py",
    )
    ok, payload = fn(limit=20, offset=40)

    assert ok is True and payload == []
    assert calls == [("sessions:list:20:40", "/sessions/?limit=20&offset=40", 10.0)]


def test_merge_loaded_sessions_reaches_older_pages_without_duplicates():
    fn = _exec_function(
        SIDEBAR_SOURCE,
        "_merge_loaded_sessions",
        {},
        "sidebar.py",
    )
    first_page = [{"session_id": f"S-{index}"} for index in range(1, 21)]
    second_page = [{"session_id": f"S-{index}"} for index in range(21, 41)]
    third_page = [{"session_id": f"S-{index}"} for index in range(41, 46)]
    merged = fn(first_page, [second_page, third_page])

    assert len(merged) == 45
    assert merged[0]["session_id"] == "S-1"
    assert merged[20]["session_id"] == "S-21"
    assert merged[-1]["session_id"] == "S-45"


def test_merge_loaded_sessions_prefers_fresh_first_page():
    fn = _exec_function(SIDEBAR_SOURCE, "_merge_loaded_sessions", {}, "sidebar.py")
    merged = fn(
        [{"session_id": "S-1", "session_name": "fresh"}],
        [[{"session_id": "S-1", "session_name": "stale"}, {"session_id": "S-2"}]],
    )
    assert merged == [
        {"session_id": "S-1", "session_name": "fresh"},
        {"session_id": "S-2"},
    ]


def test_eval_and_redteam_panels_lazy_load_before_network_reads():
    redteam_fn = EVAL_SOURCE[
        EVAL_SOURCE.index("def render_redteam_section") : EVAL_SOURCE.index("def render_eval_panel")
    ]
    assert "st.toggle(" in redteam_fn
    assert 'key=f"redteam_load_{st.session_state.session_id}"' in redteam_fn
    assert redteam_fn.index("st.toggle(") < redteam_fn.index("list_redteam_cases(")

    eval_fn = EVAL_SOURCE[EVAL_SOURCE.index("def render_eval_panel") :]
    assert "st.toggle(" in eval_fn
    assert 'key=f"eval_load_{st.session_state.session_id}"' in eval_fn
    assert eval_fn.index("st.toggle(") < eval_fn.index("list_eval_cases(")
