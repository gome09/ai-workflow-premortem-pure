# frontend/components/safety_panel.py
from __future__ import annotations

import streamlit as st


def render_safety_panel(findings: list[dict]) -> None:
    """Display SafetyFinding list with severity, status, description, and
    governance linkage. High/critical unresolved findings get visible warnings.
    Does NOT include action buttons (handled inline in app.py via official API)."""
    st.subheader("Safety Findings")
    if not findings:
        st.caption("No open safety findings.")
        return

    open_count = sum(1 for f in findings if f.get("status") == "open")
    high_crit_count = sum(
        1
        for f in findings
        if f.get("status") == "open" and f.get("severity") in {"high", "critical"}
    )
    st.caption(
        f"{len(findings)} total · {open_count} open · {high_crit_count} high/critical unresolved"
    )

    for finding in findings:
        finding_id = finding.get("finding_id", "")
        severity = finding.get("severity", "low")
        status = finding.get("status", "open")
        risk_type = finding.get("risk_type", "")
        description = finding.get("description", "")
        recommended = finding.get("recommended_action", "")
        requires_review = finding.get("requires_human_review", False)
        stage_id = finding.get("stage_id", "?")

        is_high_crit = severity in {"high", "critical"}
        is_open = status == "open"
        unresolved_warning = is_high_crit and is_open

        severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(
            severity, "⚪"
        )
        expander_label = (
            f"{severity_icon} `{finding_id}` · {severity}/{risk_type} · {status} · stage={stage_id}"
        )
        with st.expander(expander_label, expanded=unresolved_warning):
            st.code(finding_id, language="text")
            st.caption(
                f"Severity: **{severity.upper()}**  ·  "
                f"Risk type: {risk_type}  ·  "
                f"Status: {status}  ·  "
                f"Stage: {stage_id}"
            )
            if requires_review:
                st.caption("Requires human review: yes")
            if description:
                st.markdown(description)
            if recommended:
                st.caption(f"Recommended action: {recommended}")
            if unresolved_warning:
                st.warning("High/critical unresolved safety finding — may block stage advancement.")
