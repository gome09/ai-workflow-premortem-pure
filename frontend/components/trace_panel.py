# frontend/components/trace_panel.py
from __future__ import annotations

import streamlit as st


def render_trace_panel(traces: list[dict]) -> None:
    """Minimal trace explorer for stage advancement finalization."""
    st.subheader("Trace Panel")
    if not traces:
        st.caption("No traces recorded yet.")
        return

    parser_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for trace in traces:
        parser_counts[trace.get("parser_status", "unknown")] = (
            parser_counts.get(trace.get("parser_status", "unknown"), 0) + 1
        )
        type_counts[trace.get("trace_type", "unknown")] = (
            type_counts.get(trace.get("trace_type", "unknown"), 0) + 1
        )

    st.caption(f"{len(traces)} trace(s)")
    st.json({"trace_type_counts": type_counts, "parser_status_counts": parser_counts})

    for trace in reversed(traces[-50:]):
        trace_id = trace.get("trace_id", "")
        label = (
            f"{trace.get('created_at', '')[:19]} · "
            f"{trace.get('trace_type', 'trace')} · "
            f"S{trace.get('stage', '-')}"
            f" · {trace.get('parser_status', '')}"
        )
        with st.expander(label, expanded=False):
            st.code(trace_id, language="text")
            st.caption(
                f"node={trace.get('node_name', '')} · model={trace.get('model', '')} · "
                f"latency_ms={trace.get('latency_ms')}"
            )
            if trace.get("error_type") or trace.get("error_message"):
                st.error(f"{trace.get('error_type')}: {trace.get('error_message')}")
            metadata = trace.get("metadata") or {}
            if metadata:
                st.json(metadata)
            st.caption(
                "Failed/parser/safety traces can be backfilled to EvalCase through the trace API."
            )
