# frontend/components/gate_diagnosis.py
"""Gate Decision Path Visualisation — Streamlit component.

Usage::

    from frontend.components.gate_diagnosis import render_gate_diagnosis
    render_gate_diagnosis(session_id="abc", stage=3)
"""

from __future__ import annotations

import streamlit as st

from frontend.api_client import api_get


def render_gate_diagnosis(session_id: str, stage: int, base_url: str = "") -> None:
    """Render a per-rule gate diagnosis panel inside an expander.

    Parameters
    ----------
    session_id:
        Active session identifier.
    stage:
        Stage number (1–4) to retrieve the gate report for.
    base_url:
        API base URL.  Falls back to Streamlit session state
        ``api_base_url`` when empty.
    """
    if not base_url:
        base_url = st.session_state.get("api_base_url", "http://localhost:8000")

    with st.expander("Gate 诊断", expanded=False):
        try:
            report = api_get(base_url, f"/sessions/{session_id}/gate-report", stage=stage)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Gate 诊断加载失败: {exc}")
            return

        if not isinstance(report, dict):
            st.error("无效的 Gate 报告响应。")
            return

        overall = report.get("overall", "unknown")
        risk_profile = report.get("risk_profile", "unknown")
        evaluated_at = report.get("evaluated_at", "")

        # ── Summary header ──────────────────────────────────────────────────
        overall_icon = "✅" if overall == "passed" else "⛔"
        st.markdown(
            f"**{overall_icon} Stage {report.get('stage')} — "
            f"{overall.upper()}** &nbsp;&nbsp; `risk: {risk_profile}`"
        )
        if evaluated_at:
            st.caption(f"Evaluated at: {evaluated_at}")

        summary = report.get("summary") or {}
        col_t, col_p, col_b, col_s = st.columns(4)
        col_t.metric("Total rules", summary.get("total", 0))
        col_p.metric("Passed", summary.get("passed", 0))
        col_b.metric("Blocked", summary.get("blocked", 0))
        col_s.metric("Skipped", summary.get("skipped", 0))

        st.divider()

        # ── Per-rule list ────────────────────────────────────────────────────
        rules = report.get("rules") or []
        if not rules:
            st.caption("No rule details available.")
            return

        for rule in rules:
            status = rule.get("status", "unknown")
            if status == "passed":
                icon = "✅"
            elif status == "blocked":
                icon = "⛔"
            else:
                icon = "⏭"

            display_name = rule.get("display_name") or rule.get("rule_id", "Unknown Rule")
            severity = rule.get("severity")
            severity_badge = f" `{severity}`" if severity else ""

            st.markdown(f"{icon} **{display_name}**{severity_badge} — `{status}`")

            if status == "blocked" and rule.get("reason"):
                st.caption(f"Reason: {rule['reason']}")

            if status == "skipped" and rule.get("skipped_reason"):
                st.caption(f"Skipped: {rule['skipped_reason']}")
