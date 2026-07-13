# frontend/components/redteam_panel.py
from __future__ import annotations

import streamlit as st


def render_redteam_panel(*, cases: list[dict], coverage: dict) -> None:
    """Minimal Red Team coverage panel."""

    st.subheader("Red Team Coverage")
    st.caption(
        "RedTeamCase drafts must be approved, synced to EvalCase, "
        "and grouped into a redteam_generated EvalDataset before Stage 3 advancement."
    )
    cols = st.columns(4)
    cols[0].metric("RedTeamCases", coverage.get("total_cases", len(cases)))
    cols[1].metric("Draft", coverage.get("draft_cases", 0))
    cols[2].metric("Approved", coverage.get("approved_cases", 0))
    cols[3].metric("Synced", coverage.get("synced_cases", 0))

    if coverage.get("blocking"):
        st.warning("Red Team coverage is currently blocking Stage 3 advancement.")
    else:
        st.success("Red Team coverage gate has no current blockers.")

    gaps = {
        "Missing SafetyFinding coverage": coverage.get("missing_safety_finding_ids") or [],
        "Missing node coverage": coverage.get("missing_node_ids") or [],
        "Draft high-risk cases": coverage.get("draft_high_case_ids") or [],
        "Approved but unsynced cases": coverage.get("approved_unsynced_case_ids") or [],
        "Synced EvalCases outside redteam dataset": coverage.get(
            "synced_eval_ids_without_redteam_dataset"
        )
        or [],
    }
    for label, values in gaps.items():
        if values:
            st.caption(f"{label}: {', '.join(values)}")

    for case in cases:
        with st.expander(
            f"{case.get('status')} · {case.get('redteam_case_id')} · {case.get('attack_type')}",
            expanded=False,
        ):
            st.caption(
                f"severity={case.get('severity')} · target_node={case.get('target_node_id') or '-'} · "
                f"finding={case.get('source_finding_id') or '-'} · failure_mode={case.get('source_failure_mode_id') or '-'}"
            )
            st.markdown("**Prompt**")
            st.write(case.get("prompt") or "")
            st.markdown("**Expected safe behavior**")
            st.write(case.get("expected_safe_behavior") or "")
            if case.get("taxonomy_refs"):
                st.caption("taxonomy_refs=" + ", ".join(case.get("taxonomy_refs") or []))
            if case.get("control_refs"):
                st.caption("control_refs=" + ", ".join(case.get("control_refs") or []))
            if case.get("linked_eval_case_id"):
                st.caption(f"linked_eval_case_id={case.get('linked_eval_case_id')}")
