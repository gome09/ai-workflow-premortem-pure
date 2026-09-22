"""侧栏会话右键重命名的前端契约测试。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "frontend" / "app.py").read_text(encoding="utf-8")
COMPONENT_SOURCE = (
    ROOT / "frontend" / "components" / "session_item_component" / "index.html"
).read_text(encoding="utf-8")


def test_session_item_uses_right_click_to_enter_edit_mode():
    assert 'addEventListener("contextmenu", startEditing)' in COMPONENT_SOURCE
    assert "event.preventDefault()" in COMPONENT_SOURCE
    assert 'editor.style.display = "block"' in COMPONENT_SOURCE
    assert "background: transparent" in COMPONENT_SOURCE
    assert "#editor::selection" in COMPONENT_SOURCE
    assert 'item.style.display = "none"' not in COMPONENT_SOURCE


def test_session_item_saves_on_enter_or_blur():
    assert 'event.key === "Enter"' in COMPONENT_SOURCE
    assert "editor.blur()" in COMPONENT_SOURCE
    assert 'addEventListener("blur", finishEditing)' in COMPONENT_SOURCE
    assert 'emit("rename", { name: nextName })' in COMPONENT_SOURCE


def test_frontend_calls_rename_endpoint_and_prefers_session_name():
    assert 'api_patch(f"/sessions/{session_id}/name", {"name": name})' in APP_SOURCE
    assert 's.get("session_name")' in APP_SOURCE
    assert "consume_session_event(" in APP_SOURCE


def test_delete_button_matches_session_height_and_is_square():
    assert "height: 38px" in COMPONENT_SOURCE
    assert "flex: 0 0 38px" in COMPONENT_SOURCE
    assert "width: 38px" in COMPONENT_SOURCE
    assert 'deleteButton.addEventListener("click", () => emit("delete"))' in COMPONENT_SOURCE
    assert "can_delete=is_admin" in APP_SOURCE


def test_session_and_delete_boxes_share_gray_theme_with_visible_gap():
    assert "gap: 1rem" in COMPONENT_SOURCE
    assert "background: var(--sidebar-background)" in COMPONENT_SOURCE
    assert COMPONENT_SOURCE.count("background: transparent") >= 4
    assert "--sidebar-background: #262730" in COMPONENT_SOURCE
    assert "event.data.theme?.secondaryBackgroundColor" not in COMPONENT_SOURCE
