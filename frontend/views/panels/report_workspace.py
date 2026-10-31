# frontend/views/panels/report_workspace.py
from __future__ import annotations

import json

import streamlit as st
from components.report_panel import render_report_panel
from controllers.report_controller import create_snapshot, export_snapshot, load_snapshot
from models.api_client import list_report_artifacts


def render_report_workspace() -> None:
    st.subheader("报告工作台")

    # --- 导出实时快照 ---
    with st.expander("导出实时快照", expanded=False):
        col_json, col_md = st.columns(2)
        with col_json:
            if st.button("生成 JSON", use_container_width=True, key="export_json_btn"):
                report = export_snapshot("json")
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
                else:
                    st.error("生成 JSON 报告失败，请稍后重试。")
        with col_md:
            if st.button("生成 Markdown", use_container_width=True, key="export_md_btn"):
                report = export_snapshot("markdown")
                if report and report.get("content"):
                    sid_short = st.session_state.session_id[:8]
                    st.download_button(
                        label="下载 Markdown",
                        data=report["content"],
                        file_name=f"workflow_report_{sid_short}.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )
                else:
                    st.error("生成 Markdown 报告失败，请稍后重试。")

    # --- 版本化报告快照 ---
    st.divider()
    if st.button("创建报告快照", use_container_width=True, key="create_artifact_btn"):
        create_snapshot()

    artifacts = list_report_artifacts(st.session_state.session_id)
    if artifacts:
        report_options = {
            f"{a.get('report_id', '?')[:12]}... (v{a.get('version', '?')}, {a.get('generated_at', '?')[:19]})": a
            for a in reversed(artifacts[-20:])
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
            full_report = load_snapshot(report_id)
            if full_report:
                render_report_panel(full_report)
            else:
                st.error(f"加载报告 {report_id} 失败，后端可能暂时不可用。")
        else:
            st.caption("尚未选择报告，请在上方下拉框中选择一个查看。")
    else:
        st.info("暂无报告快照。可在上方创建快照或导出实时报告。")
