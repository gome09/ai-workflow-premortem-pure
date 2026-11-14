# frontend/views/panels/report_workspace.py
from __future__ import annotations

import json

import streamlit as st
from components.report_panel import render_report_panel
from controllers.report_controller import create_snapshot, export_snapshot, load_snapshot
from models.api_client import list_report_artifacts_checked
from models.feedback import ApiError, show_api_error


def render_report_workspace() -> None:
    st.subheader("报告工作台")

    # --- 导出实时快照 ---
    with st.expander("导出实时快照", expanded=False):
        col_json, col_md = st.columns(2)
        with col_json:
            if st.button("生成 JSON", use_container_width=True, key="export_json_btn"):
                try:
                    report = export_snapshot("json")
                except ApiError as exc:
                    show_api_error(exc)
                    report = None
                if report:
                    report_json = json.dumps(report, ensure_ascii=False, indent=2)
                    sid_short = st.session_state.session_id[:8]
                    st.download_button(
                        label="下载 JSON",
                        data=report_json,
                        file_name=f"workflow_report_{sid_short}.json",
                        mime="application/json",
                        use_container_width=True,
                    )
        with col_md:
            if st.button("生成 Markdown", use_container_width=True, key="export_md_btn"):
                try:
                    report = export_snapshot("markdown")
                except ApiError as exc:
                    show_api_error(exc)
                    report = None
                if report and report.get("content"):
                    sid_short = st.session_state.session_id[:8]
                    st.download_button(
                        label="下载 Markdown",
                        data=report["content"],
                        file_name=f"workflow_report_{sid_short}.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )

    # --- 版本化报告快照 ---
    st.divider()
    if st.button("创建报告快照", use_container_width=True, key="create_artifact_btn"):
        create_snapshot()

    artifacts_ok, artifacts_payload = list_report_artifacts_checked(st.session_state.session_id)
    if not artifacts_ok:
        st.warning("无法读取报告快照列表，请稍后刷新重试。")
        return
    artifacts = artifacts_payload if isinstance(artifacts_payload, list) else []
    if artifacts:
        limit = max(int(st.session_state.get("report_list_limit", 20)), 20)
        st.caption(f"共 {len(artifacts)} 份快照，按生成时间倒序（最新在前）。")
        report_options = {
            f"{a.get('report_id', '?')[:12]}... (v{a.get('version', '?')}, {a.get('generated_at', '?')[:19]})": a
            for a in artifacts[:limit]
        }
        selected_label = st.selectbox(
            "选择要查看的报告快照",
            options=["[无]"] + list(report_options.keys()),
            key="selected_report_label",
        )
        if selected_label and selected_label != "[无]":
            selected_artifact = report_options[selected_label]
            report_id = selected_artifact.get("report_id", "")
            # 从接口获取完整快照（含 content_json / content_markdown）
            try:
                full_report = load_snapshot(report_id)
            except ApiError as exc:
                show_api_error(exc)
                full_report = None
            if full_report:
                render_report_panel(full_report)
        else:
            st.caption("尚未选择报告，请在上方下拉框中选择一个查看。")
        if len(artifacts) > limit:
            if st.button(
                "显示更多（+20）",
                key="load_more_reports",
                use_container_width=True,
            ):
                st.session_state.report_list_limit = limit + 20
                st.rerun()
    else:
        st.info("暂无报告快照。可在上方创建快照或导出实时报告。")
