# frontend/controllers/report_controller.py
from __future__ import annotations

import streamlit as st
from models.api_client import create_report_artifact, export_report, get_report_artifact


def export_snapshot(fmt: str) -> dict | None:
    with st.spinner("正在生成..."):
        report = export_report(st.session_state.session_id, format=fmt)
    return report


def create_snapshot() -> None:
    artifact = create_report_artifact(st.session_state.session_id)
    if artifact:
        st.success(f"快照已创建：{artifact.get('report_id')}")
    else:
        st.error("创建报告快照失败，请稍后重试。")


def load_snapshot(report_id: str) -> dict | None:
    return get_report_artifact(st.session_state.session_id, report_id)
