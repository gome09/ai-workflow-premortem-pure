# frontend/state.py
from __future__ import annotations

import streamlit as st

DEFAULT_KEYS = {
    "api_base_url": "http://localhost:8000",
    "session_id": None,
    "selected_action_id": None,
}


def init_state() -> None:
    for key, value in DEFAULT_KEYS.items():
        st.session_state.setdefault(key, value)
