# frontend/models/stage_envelope.py
from __future__ import annotations

import streamlit as st


def apply_stage_operation_result(result: dict | None) -> dict | None:
    """Consume the current StageOperationEnvelope shape in one place.

    Mutating operations return domain payloads plus
    stage_advancement_decision / next_required_operation. The frontend keeps the
    domain behavior but stores the canonical advancement view and invalidates
    cached readiness/resolution panels so the next render fetches fresh data.
    """
    if not isinstance(result, dict):
        return result

    decision = result.get("stage_advancement_decision")
    if isinstance(decision, dict):
        st.session_state.stage_advancement_decision = decision
        stage_id = decision.get("stage_id")
        if stage_id is not None:
            decisions = dict(st.session_state.get("stage_advancement_decisions", {}))
            decisions[str(stage_id)] = decision
            decisions[f"stage_{stage_id}"] = decision
            st.session_state.stage_advancement_decisions = decisions

    next_operation = result.get("next_required_operation")
    if next_operation is not None:
        st.session_state.next_required_operation = next_operation

    if result.get("current_state"):
        st.session_state.current_state = result.get("current_state")
    elif isinstance(decision, dict) and decision.get("current_state"):
        st.session_state.current_state = decision.get("current_state")

    if isinstance(result.get("interrupt_records"), list):
        st.session_state.interrupt_records = result.get("interrupt_records", [])
    if isinstance(result.get("pending_actions"), list):
        st.session_state.pending_actions = [
            action
            for action in result.get("pending_actions", [])
            if action.get("status") == "pending"
        ]

    st.session_state.stage_readiness = {}
    st.session_state.stage_resolution = {}
    return result


def stage_operation_items(result: dict | list | None) -> list[dict]:
    """Return list-style domain items while preserving StageOperationEnvelope state."""
    if isinstance(result, list):
        return result
    applied = apply_stage_operation_result(result if isinstance(result, dict) else None)
    if isinstance(applied, dict):
        for key in ("items", "result"):
            value = applied.get(key)
            if isinstance(value, list):
                return value
    return []
