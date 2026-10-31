"""双主题配置、会话条目可访问性与图表色彩契约测试。"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
CONFIG_PATH = ROOT / ".streamlit" / "config.toml"
INDEX_HTML_PATH = FRONTEND_DIR / "components" / "session_item_component" / "index.html"
SESSION_ITEM_SOURCE = (FRONTEND_DIR / "components" / "session_item.py").read_text(encoding="utf-8")
GOVERNANCE_SOURCE = (FRONTEND_DIR / "components" / "governance_overview.py").read_text(
    encoding="utf-8"
)


def _theme_config() -> dict:
    return tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_theme_config_declares_light_and_dark_palettes():
    config = _theme_config()
    theme = config["theme"]
    assert theme["primaryColor"] == "#4C8BF5"
    for base in ("light", "dark"):
        palette = theme[base]
        for key in ("backgroundColor", "secondaryBackgroundColor", "textColor"):
            assert key in palette, f"[theme.{base}] 缺少 {key}"
    assert config["server"]["headless"] is True


def test_session_item_html_has_no_fixed_sidebar_background():
    """组件底色必须由当前主题动态注入，不能写死侧栏颜色。"""
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    assert "--sidebar-background" not in html
    assert "color-scheme" not in html
    assert "--session-item-background" in html
    assert "setProperty(" in html


def test_session_item_is_keyboard_accessible():
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    assert 'role="button"' in html
    assert 'tabindex="0"' in html
    assert "F2" in html
    assert 'aria-label="会话名称"' in html
    # 可见的重命名按钮，避免只能依赖右键/F2 才能发现该操作
    assert 'id="rename-button"' in html


def test_theme_detection_falls_back_to_dark_without_context_theme():
    assert 'getattr(st.context, "theme", None)' in SESSION_ITEM_SOURCE
    assert 'theme_type != "light"' in SESSION_ITEM_SOURCE


def test_governance_charts_have_no_hardcoded_white_text_layer():
    """图表配色必须可随主题保持可读，不能叠一层白色文字标签。"""
    assert "mark_text(" not in GOVERNANCE_SOURCE
    assert 'color="white"' not in GOVERNANCE_SOURCE
    assert 'color="#4C8BF5"' in GOVERNANCE_SOURCE
