"""侧栏会话列表搜索/分页与评测面板懒加载的前端契约测试。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIDEBAR_SOURCE = (ROOT / "frontend" / "views" / "sidebar.py").read_text(encoding="utf-8")
EVAL_SOURCE = (ROOT / "frontend" / "views" / "panels" / "eval_panels.py").read_text(encoding="utf-8")


def test_session_list_supports_local_search():
    assert "key=\"session_filter\"" in SIDEBAR_SOURCE
    assert "_SESSION_SEARCH_FIELDS" in SIDEBAR_SOURCE
    assert "visible_sessions" in SIDEBAR_SOURCE


def test_session_list_paginates_twenty_at_a_time():
    assert "_SESSION_PAGE_SIZE = 20" in SIDEBAR_SOURCE
    assert "session_list_limit" in SIDEBAR_SOURCE
    assert "显示更多（+20）" in SIDEBAR_SOURCE
    assert "sessions[:10]" not in SIDEBAR_SOURCE


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
