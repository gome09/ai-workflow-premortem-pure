"""侧栏会话右键重命名的前端契约测试。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_SOURCES = {
    path: path.read_text(encoding="utf-8") for path in sorted(FRONTEND_DIR.rglob("*.py"))
}
SOURCE = "\n".join(FRONTEND_SOURCES.values())
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
    assert 'api_patch(f"/sessions/{session_id}/name", {"name": name})' in SOURCE
    assert 's.get("session_name")' in SOURCE
    assert "consume_session_event(" in SOURCE


def test_delete_button_matches_session_height_and_is_square():
    assert "height: 38px" in COMPONENT_SOURCE
    assert "flex: 0 0 38px" in COMPONENT_SOURCE
    assert "width: 38px" in COMPONENT_SOURCE
    assert 'deleteButton.addEventListener("click", () => emit("delete"))' in COMPONENT_SOURCE
    assert "can_delete=is_admin" in SOURCE


def test_session_item_is_keyboard_accessible():
    assert 'role="button"' in COMPONENT_SOURCE
    assert 'tabindex="0"' in COMPONENT_SOURCE
    assert 'item.setAttribute("aria-label"' in COMPONENT_SOURCE
    assert 'event.key === "Enter" || event.key === " "' in COMPONENT_SOURCE
    assert 'event.key === "F2"' in COMPONENT_SOURCE
    assert 'renameButton.addEventListener("click", startEditing)' in COMPONENT_SOURCE


def test_session_item_renders_visible_rename_button():
    assert 'id="rename-button"' in COMPONENT_SOURCE
    assert 'renameButton.style.display = args.disabled ? "none" : "flex"' in COMPONENT_SOURCE


def test_session_item_receives_state_label_from_sidebar():
    assert 'state_label: str = ""' in SOURCE
    assert "state_label=state_label" in SOURCE


def test_reasoning_is_rendered_without_unsafe_html():
    assert "unsafe_allow_html" not in SOURCE


def test_session_and_delete_boxes_share_gray_theme_with_visible_gap():
    assert "gap: 1rem" in COMPONENT_SOURCE
    assert "background: var(--sidebar-background)" in COMPONENT_SOURCE
    assert COMPONENT_SOURCE.count("background: transparent") >= 4
    assert "--sidebar-background: #262730" in COMPONENT_SOURCE
    assert "event.data.theme?.secondaryBackgroundColor" not in COMPONENT_SOURCE
