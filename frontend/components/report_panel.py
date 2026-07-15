# frontend/components/report_panel.py
from __future__ import annotations

import json

import streamlit as st
from labels import decision_scope_zh, decision_zh, severity_zh, status_zh


def render_report_panel(report: dict) -> None:
    """展示单个报告快照：Markdown、治理信息与 JSON 下载。"""
    st.subheader("报告预览")

    if not report:
        st.caption("未加载报告。")
        return

    report_id = report.get("report_id", "")
    version = report.get("version", "")
    generated_at = report.get("generated_at", "")
    if report_id:
        st.caption(f"报告 ID：`{report_id}`  ·  版本：`{version}`  ·  生成时间：{generated_at}")

    content_json = report.get("content_json") or {}
    content_md = report.get("content_markdown") or ""

    # ── Markdown 展示 ────────────────────────────────────────────────────────
    with st.expander("Markdown 报告", expanded=bool(content_md)):
        if content_md:
            st.markdown(content_md)
        else:
            st.caption("暂无 Markdown 内容。")

    # ── JSON 下载 ────────────────────────────────────────────────────────────
    with st.expander("JSON 报告（完整）", expanded=False):
        st.download_button(
            label="下载 JSON",
            data=json.dumps(content_json, ensure_ascii=False, indent=2),
            file_name=f"report_{report_id or 'artifact'}.json",
            mime="application/json",
            use_container_width=True,
        )
        if not content_json:
            st.caption("暂无 JSON 内容。")

    # ── 治理与审计摘要 ───────────────────────────────────────────────────────
    with st.expander("治理与审计摘要", expanded=True):
        _render_governance_section(content_json)

    # ── 部署门禁决策 ─────────────────────────────────────────────────────────
    _render_deployment_decision(content_json)


def _render_governance_section(content: dict) -> None:
    """从报告 content_json 渲染治理 / 审计 / 风险相关内容。"""

    # 人工审核摘要
    oversight = content.get("oversight_summary") or {}
    if oversight:
        st.markdown("#### 人工审核")
        col1, col2, col3 = st.columns(3)
        col1.metric("动作总数", oversight.get("total_actions", 0))
        col2.metric(
            "待处理（阻断型）",
            f"{oversight.get('pending_actions', 0)} ({oversight.get('pending_blocking_actions', 0)})",
        )
        col3.metric(
            "已处理 / 已驳回",
            f"{oversight.get('resolved_actions', 0)} / {oversight.get('rejected_actions', 0)}",
        )
        if oversight.get("critical_escalations"):
            st.warning(f"危急升级项：{oversight['critical_escalations']}")

    # 未关闭风险（content_json 顶层，status=open 的安全发现）
    open_risks = content.get("open_risks") or []
    if open_risks:
        st.markdown("#### 未关闭风险")
        st.caption(f"待处理安全发现 {len(open_risks)} 项")
        for risk in open_risks[:5]:
            st.text(
                f"- [{severity_zh(risk.get('severity', '?'))}] {risk.get('finding_id', '?')}："
                f"{risk.get('message', risk.get('description', ''))}"
            )

    # 全部安全发现
    safety = content.get("safety_findings") or []
    if safety:
        open_count = len([s for s in safety if s.get("status") == "open"])
        st.markdown(f"#### 安全发现（共 {len(safety)} 项，待处理 {open_count} 项）")
        for s in safety[:5]:
            severity = severity_zh(s.get("severity", "?"))
            finding_id = s.get("finding_id", s.get("id", "?"))
            msg = s.get("message", s.get("description", ""))
            status = status_zh(s.get("status", "?"))
            st.text(f"- [{severity}] {finding_id}（{status}）：{msg}")

    # 证据摘要
    evidence_summary = content.get("evidence_summary") or {}
    if evidence_summary:
        st.markdown("#### 证据")
        col1, col2, col3 = st.columns(3)
        col1.metric("证据来源总数", evidence_summary.get("total_evidence_sources", 0))
        col2.metric("已核验", evidence_summary.get("verified_sources", 0))
        col3.metric("低可信", evidence_summary.get("low_credibility_sources", 0))
        without_ev = evidence_summary.get("failure_modes_without_evidence_count", 0)
        if without_ev:
            st.caption(f"缺少证据的失败模式：{without_ev}")

    # 评测摘要
    eval_summary = content.get("eval_summary") or {}
    if eval_summary:
        st.markdown("#### 评测覆盖")
        col1, col2, col3 = st.columns(3)
        col1.metric("用例总数", eval_summary.get("total_eval_cases", 0))
        col2.metric("覆盖率 %", f"{eval_summary.get('coverage_percent', 0):.1f}")
        col3.metric("失败运行数", eval_summary.get("failed_eval_runs", 0))

    # 阶段就绪情况
    stage_readiness = content.get("stage_readiness") or {}
    if stage_readiness:
        st.markdown("#### 阶段就绪情况")
        for stage_key, stage_data in stage_readiness.items():
            if isinstance(stage_data, dict):
                blockers = stage_data.get("blockers") or []
                can_cont = "可推进" if stage_data.get("can_continue") else "已阻断"
                st.caption(f"{stage_key}：{can_cont}（{len(blockers)} 个阻断项）")

    # 报告导出状态
    export_status = content.get("report_export_status") or {}
    if export_status:
        allowed = export_status.get("allowed", False)
        reason = export_status.get("reason", "")
        if allowed:
            st.success("报告导出状态：满足审计要求")
        else:
            st.warning(f"报告导出状态：尚未满足审计要求 —— {reason}")

    # 未闭环治理事项
    unresolved = content.get("unresolved_governance_items") or {}
    if unresolved:
        stage_blockers = unresolved.get("stage_blockers") or []
        pending_actions = unresolved.get("pending_actions") or []
        parser_errors = unresolved.get("parser_errors") or []
        if stage_blockers:
            st.markdown("##### 阶段阻断项")
            for b in stage_blockers[:5]:
                st.text(
                    f"- [{severity_zh(b.get('severity', '?'))}] {b.get('blocker_id', '?')}："
                    f"{b.get('message', '')}"
                )
        if pending_actions:
            st.caption(f"待处理治理动作：{len(pending_actions)}")
        if parser_errors:
            st.caption(f"解析错误：{len(parser_errors)}")

    # 审计事件数
    audit_events = content.get("audit_events") or []
    if audit_events:
        st.caption(f"已记录审计事件：{len(audit_events)}")

    # 未关闭动作
    open_actions = content.get("open_actions") or []
    if open_actions:
        st.caption(f"未关闭动作：{len(open_actions)}")
        for a in open_actions[:5]:
            st.text(
                f"- [{a.get('action_type', '?')}] {a.get('action_id', '?')}"
                f"（{status_zh(a.get('status', '?'))}）"
            )

    # 完全没有数据时
    has_any = any(
        [
            oversight,
            open_risks,
            safety,
            evidence_summary,
            eval_summary,
            stage_readiness,
            export_status,
            unresolved,
            audit_events,
            open_actions,
        ]
    )
    if not has_any:
        st.caption("本报告暂无治理数据。")


def _render_deployment_decision(content: dict) -> None:
    """渲染 Stage 4 部署门禁决策卡片（当 deployment_decision 存在时）。"""
    stage_4 = (content.get("ai_generated") or {}).get("stage_4") or {}
    decision = stage_4.get("deployment_decision")
    if not decision:
        return

    decision_label = decision_zh(decision.get("decision"))
    scope_label = decision_scope_zh(decision.get("decision_scope"))
    title = f"🚦 部署门禁决策：{decision_label}"
    if scope_label and scope_label != "-":
        title += f" · {scope_label}"
    with st.expander(title, expanded=True):
        col1, col2 = st.columns(2)
        col1.metric("决策", decision_label)
        col2.metric("部署范围", scope_label)

        rationale = decision.get("decision_rationale") or ""
        if rationale:
            st.markdown(f"**决策依据：** {rationale}")

        def _render_list(heading: str, items: object) -> None:
            values = items or []
            if not values:
                return
            st.markdown(f"**{heading}**")
            for item in values:
                st.text(f"- {item}")

        _render_list("未解决风险 ID", decision.get("unresolved_risk_ids"))
        _render_list("前置条件", decision.get("required_conditions"))
        _render_list("所需审批", decision.get("required_approvals"))
        _render_list("监控要求", decision.get("monitoring_requirements"))
        _render_list("回滚条件", decision.get("rollback_conditions"))
        _render_list("禁止用途", decision.get("prohibited_uses"))

        review_after = decision.get("review_after") or ""
        if review_after:
            st.markdown(f"**复审时机：** {review_after}")

        accountable = decision.get("human_accountable_role") or ""
        if accountable:
            st.markdown(f"**人工问责角色：** {accountable}")

        if decision.get("is_demo_recommendation"):
            st.warning(
                "⚠️ 本决策为演示推荐（demo recommendation），基于演示数据生成，"
                "未连接真实模型评测；评估完成 ≠ 正式批准部署。"
            )
