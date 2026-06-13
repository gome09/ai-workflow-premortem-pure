# frontend/components/report_panel.py
from __future__ import annotations

import json

import streamlit as st


def render_report_panel(report: dict) -> None:
    """Display a single ReportArtifact with markdown, governance info, and JSON download."""
    st.subheader("Report Preview")

    if not report:
        st.caption("No report loaded.")
        return

    report_id = report.get("report_id", "")
    version = report.get("version", "")
    generated_at = report.get("generated_at", "")
    if report_id:
        st.caption(
            f"report_id: `{report_id}`  ·  version: `{version}`  ·  generated: {generated_at}"
        )

    content_json = report.get("content_json") or {}
    content_md = report.get("content_markdown") or ""

    # ── Markdown Display ─────────────────────────────────────────────────────
    with st.expander("Markdown Report", expanded=bool(content_md)):
        if content_md:
            st.markdown(content_md)
        else:
            st.caption("No markdown content available.")

    # ── JSON Download ────────────────────────────────────────────────────────
    with st.expander("JSON Report (full)", expanded=False):
        st.download_button(
            label="Download JSON",
            data=json.dumps(content_json, ensure_ascii=False, indent=2),
            file_name=f"report_{report_id or 'artifact'}.json",
            mime="application/json",
            use_container_width=True,
        )
        if not content_json:
            st.caption("No JSON content available.")

    # ── Governance Summary ───────────────────────────────────────────────────
    with st.expander("Governance & Audit Summary", expanded=True):
        _render_governance_section(content_json)


def _render_governance_section(content: dict) -> None:
    """Render governance/audit/risk sections from report content_json."""

    # Oversight summary
    oversight = content.get("oversight_summary") or {}
    if oversight:
        st.markdown("#### Human Oversight")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Actions", oversight.get("total_actions", 0))
        col2.metric(
            "Pending (Blocking)",
            f"{oversight.get('pending_actions', 0)} ({oversight.get('pending_blocking_actions', 0)})",
        )
        col3.metric(
            "Resolved / Rejected",
            f"{oversight.get('resolved_actions', 0)} / {oversight.get('rejected_actions', 0)}",
        )
        if oversight.get("critical_escalations"):
            st.warning(f"Critical escalations: {oversight['critical_escalations']}")

    # Open risks (from content_json top-level, safety_findings with status=open)
    open_risks = content.get("open_risks") or []
    if open_risks:
        st.markdown("#### Open Risks")
        st.caption(f"{len(open_risks)} open safety finding(s)")
        for risk in open_risks[:5]:
            st.text(
                f"- [{risk.get('severity', '?')}] {risk.get('finding_id', '?')}: {risk.get('message', risk.get('description', ''))}"
            )

    # Safety findings (all)
    safety = content.get("safety_findings") or []
    if safety:
        open_count = len([s for s in safety if s.get("status") == "open"])
        st.markdown(f"#### Safety Findings ({len(safety)} total, {open_count} open)")
        for s in safety[:5]:
            severity = s.get("severity", "?")
            finding_id = s.get("finding_id", s.get("id", "?"))
            msg = s.get("message", s.get("description", ""))
            status = s.get("status", "?")
            st.text(f"- [{severity}] {finding_id} ({status}): {msg}")

    # Evidence summary
    evidence_summary = content.get("evidence_summary") or {}
    if evidence_summary:
        st.markdown("#### Evidence")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Sources", evidence_summary.get("total_evidence_sources", 0))
        col2.metric("Verified", evidence_summary.get("verified_sources", 0))
        col3.metric("Low Credibility", evidence_summary.get("low_credibility_sources", 0))
        without_ev = evidence_summary.get("failure_modes_without_evidence_count", 0)
        if without_ev:
            st.caption(f"Failure modes without evidence: {without_ev}")

    # Eval summary
    eval_summary = content.get("eval_summary") or {}
    if eval_summary:
        st.markdown("#### Eval Coverage")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Cases", eval_summary.get("total_eval_cases", 0))
        col2.metric("Coverage %", f"{eval_summary.get('coverage_percent', 0):.1f}")
        col3.metric("Failed Runs", eval_summary.get("failed_eval_runs", 0))

    # Stage readiness
    stage_readiness = content.get("stage_readiness") or {}
    if stage_readiness:
        st.markdown("#### Stage Readiness")
        for stage_key, stage_data in stage_readiness.items():
            if isinstance(stage_data, dict):
                blockers = stage_data.get("blockers") or []
                can_cont = "can continue" if stage_data.get("can_continue") else "blocked"
                st.caption(f"{stage_key}: {can_cont} ({len(blockers)} blocker(s))")

    # Report export status
    export_status = content.get("report_export_status") or {}
    if export_status:
        allowed = export_status.get("allowed", False)
        reason = export_status.get("reason", "")
        if allowed:
            st.success("Report export status: audit-ready")
        else:
            st.warning(f"Report export status: not audit-ready — {reason}")

    # Unresolved governance items
    unresolved = content.get("unresolved_governance_items") or {}
    if unresolved:
        stage_blockers = unresolved.get("stage_blockers") or []
        pending_actions = unresolved.get("pending_actions") or []
        parser_errors = unresolved.get("parser_errors") or []
        if stage_blockers:
            st.markdown("##### Stage Blockers")
            for b in stage_blockers[:5]:
                st.text(
                    f"- [{b.get('severity', '?')}] {b.get('blocker_id', '?')}: {b.get('message', '')}"
                )
        if pending_actions:
            st.caption(f"Pending governance actions: {len(pending_actions)}")
        if parser_errors:
            st.caption(f"Parser errors: {len(parser_errors)}")

    # Audit events count
    audit_events = content.get("audit_events") or []
    if audit_events:
        st.caption(f"Audit events recorded: {len(audit_events)}")

    # Open actions
    open_actions = content.get("open_actions") or []
    if open_actions:
        st.caption(f"Open actions: {len(open_actions)}")
        for a in open_actions[:5]:
            st.text(
                f"- [{a.get('action_type', '?')}] {a.get('action_id', '?')} ({a.get('status', '?')})"
            )

    # If nothing at all
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
        st.caption("No governance data available in this report.")
