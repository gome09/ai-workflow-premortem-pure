# frontend/components/evidence_panel.py
from __future__ import annotations

import streamlit as st


def render_evidence_panel(evidence_sources: list[dict]) -> None:
    """Display EvidenceSource list with verification status, credibility,
    failure-mode linkage, and source details. Does NOT include action buttons
    (those are handled inline in app.py via the official verify_evidence API)."""
    st.subheader("Evidence Sources")
    if not evidence_sources:
        st.caption("No evidence sources recorded.")
        return

    verified_count = sum(1 for ev in evidence_sources if ev.get("verified"))
    unverified_count = len(evidence_sources) - verified_count
    st.caption(
        f"{len(evidence_sources)} total · {verified_count} verified · {unverified_count} unverified"
    )

    for ev in evidence_sources:
        evidence_id = ev.get("evidence_id", "")
        verified = ev.get("verified", False)
        source_type = ev.get("source_type", "unknown")
        score = ev.get("credibility_score", 0.0)
        title = ev.get("title", "")
        url = ev.get("url", "")
        summary = ev.get("summary", "")
        claims = ev.get("claims", []) or []
        failure_mode_ids = ev.get("used_by_failure_mode_ids", []) or []
        verification_note = ev.get("verification_note", "")

        status_icon = "✅" if verified else "⚪"
        status_text = "verified" if verified else "unverified"
        score_color = "green" if score >= 0.7 else "orange" if score >= 0.4 else "red"

        expander_label = (
            f"{status_icon} `{evidence_id}` · {source_type} · "
            f"credibility={score:.2f} · {status_text}"
        )
        with st.expander(expander_label, expanded=(not verified and score < 0.4)):
            st.code(evidence_id, language="text")
            st.caption(
                f"Source type: {source_type}  ·  Credibility score: :{score_color}[{score:.2f}]  ·  {status_text}"
            )
            if title:
                st.markdown(f"**{title}**")
            if url:
                st.caption(f"URL: {url}")
            if summary:
                st.markdown(summary)
            if claims:
                st.caption("Claims:")
                for claim in claims:
                    st.markdown(f"- {claim}")
            if failure_mode_ids:
                st.caption("Linked failure modes: " + ", ".join(failure_mode_ids))
            if verified and verification_note:
                st.caption(f"Verification note: {verification_note}")
            if not verified and score < 0.4:
                st.warning("Low credibility — unverified sources may weaken downstream analysis.")
