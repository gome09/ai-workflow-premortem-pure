# frontend/components/audit_timeline.py
from __future__ import annotations

import streamlit as st


def render_audit_timeline(events: list[dict]) -> None:
    """Display AuditEvent history with event type, actor, timestamp, target,
    and metadata details. Governance-linked targets (action, evidence, safety,
    eval, report, stage) are preserved in the target_type/target_id display."""
    st.subheader("Audit Timeline")
    if not events:
        st.caption("No audit events recorded.")
        return

    st.caption(f"{len(events)} audit events recorded")
    for event in events:
        event_type = event.get("event_type", "?")
        actor = event.get("actor", "system")
        created_at = event.get("created_at", "")
        target_type = event.get("target_type", "")
        target_id = event.get("target_id", "")
        metadata = event.get("metadata") or {}
        before = event.get("before")
        after = event.get("after")

        # Build a descriptive label
        label = (
            f"{created_at[:19] if created_at else '?'}  ·  "
            f"{actor}  ·  "
            f"{event_type}  ·  "
            f"{target_type}/{target_id}"
        )
        with st.expander(label, expanded=False):
            st.caption(f"Event type: **{event_type}**")
            st.caption(f"Actor: {actor}")
            st.caption(f"Timestamp: {created_at}")
            st.caption(f"Target: {target_type}/{target_id}")
            if metadata:
                with st.expander("Metadata", expanded=False):
                    st.json(metadata)
            if before is not None or after is not None:
                st.caption("Diff available (before/after snapshots present)")
