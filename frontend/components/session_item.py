"""可右键编辑名称的会话列表项 Streamlit 组件。"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).with_name("session_item_component")
_session_item = components.declare_component("session_item", path=_COMPONENT_DIR)


def _is_dark_theme() -> bool:
    """读取当前主题类型；低版本无 st.context.theme 时回退为深色。"""
    theme = getattr(st.context, "theme", None)
    theme_type = getattr(theme, "type", None)
    return theme_type != "light"


def render_session_item(
    *,
    session_id: str,
    label: str,
    icon: str,
    state_label: str = "",
    domain: str = "",
    is_current: bool = False,
    disabled: bool = False,
    can_delete: bool = False,
) -> dict | None:
    """渲染会话条目并返回 select/rename/delete 事件。"""
    value = _session_item(
        session_id=session_id,
        label=label,
        icon=icon,
        state_label=state_label,
        domain=domain,
        is_current=is_current,
        is_dark=_is_dark_theme(),
        disabled=disabled,
        can_delete=can_delete,
        max_length=80,
        key=f"session_item_{session_id}",
        default=None,
    )
    return value if isinstance(value, dict) else None
