# graph/edges.py
"""Routing helper for the experimental full-graph LangGraph builder.

This module is only used by graph.builder (experimental, not production).
The production execution path (graph.runner.run_one_step) does not use this.
"""
from __future__ import annotations

from core.models import ProjectContext, SessionState


def route_by_state(state: ProjectContext) -> str:
    """
    核心路由函数：根据当前状态决定下一个节点。
    LangGraph 的条件边调用此函数。
    """
    routing_map = {
        SessionState.INIT: "node_init",
        SessionState.S1_RUNNING: "node_s1_running",
        SessionState.S1_REVIEW: "node_s1_review",
        SessionState.S2_RUNNING: "node_s2_running",
        SessionState.S2_REVIEW: "node_s2_review",
        SessionState.S3_RUNNING: "node_s3_running",
        SessionState.S3_REVIEW: "node_s3_review",
        SessionState.S4_RUNNING: "node_s4_running",
        SessionState.S4_REVIEW: "node_s4_review",
        SessionState.COMPLETE: "node_complete",
    }
    return routing_map.get(state.current_state, "node_init")
