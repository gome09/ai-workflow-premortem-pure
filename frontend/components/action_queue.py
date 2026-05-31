# frontend/components/action_queue.py
from __future__ import annotations

import streamlit as st


def render_action_queue(actions: list[dict]) -> None:
    """Display PendingHumanAction list with v0.7 action-contract diagnostics."""

    st.subheader("Pending Human Actions")
    if not actions:
        st.caption("No pending actions.")
        return

    st.caption("Blocking actions must be resolved before the stage gate will allow advancement.")
    for action in actions:
        action_id = action.get("action_id", "")
        risk = action.get("risk_level", "medium")
        action_type = action.get("action_type", "")
        title = action.get("title", "Unnamed action")
        blocking = action.get("blocking", True)
        stage_id = action.get("stage_id", "?")
        version = action.get("stage_output_version", 1)
        target_version = action.get("target_stage_version") or version
        source_type = action.get("source_type", "")
        source_id = action.get("source_id", "")
        contract_id = action.get("action_contract_id", "")
        idempotency_key = action.get("idempotency_key", "")
        superseded_by = action.get("superseded_by", "")

        blocking_label = "BLOCKING" if blocking else "non-blocking"
        expander_label = f"[S{stage_id} v{version}] {risk}/{action_type}/{blocking_label} · {title}"
        with st.expander(expander_label, expanded=blocking):
            st.code(action_id, language="text")
            st.caption(
                f"Stage {stage_id} · output version v{version} · target version v{target_version} · "
                f"{risk} risk · {blocking_label}"
            )
            if contract_id:
                st.caption(f"contract_id: `{contract_id}`")
            if idempotency_key:
                st.caption(f"idempotency_key: `{idempotency_key}`")
            if superseded_by:
                st.warning(f"Superseded by: {superseded_by}")
            if source_type or source_id:
                st.caption(f"Source: {source_type}/{source_id}")
            st.markdown(f"**{title}**")
            if action.get("description"):
                st.markdown(action["description"])
            if action.get("trigger_reason"):
                st.caption(f"Trigger: {action['trigger_reason']}")
