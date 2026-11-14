# frontend/controllers/report_controller.py
from __future__ import annotations

import streamlit as st
from models.api_client import (
    create_report_artifact,
    export_report,
    get_report_artifact,
    invalidate_session_cache,
)
from models.feedback import ApiError, show_api_error


def export_snapshot(fmt: str) -> dict:
    """导出实时报告；失败抛 ApiError，由视图在按钮边界提示一次。"""
    with st.spinner("正在生成..."):
        return export_report(st.session_state.session_id, format=fmt)


def create_snapshot() -> None:
    try:
        artifact = create_report_artifact(st.session_state.session_id)
    except ApiError as exc:
        show_api_error(exc)
        return
    invalidate_session_cache(st.session_state.session_id)
    st.success(f"快照已创建：{artifact.get('report_id')}")


def load_snapshot(report_id: str) -> dict:
    """读取版本化快照；失败抛 ApiError，由视图提示服务端 detail。"""
    return get_report_artifact(st.session_state.session_id, report_id)
