# graph/builder.py
# NOTE: Current production execution path is graph.runner.run_one_step().
# This builder is kept only as a future LangGraph interrupt/checkpoint adapter base.
from __future__ import annotations

import logging

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph

from core.config import settings
from core.models import ProjectContext
from graph.edges import route_by_state
from graph.nodes import (
    node_init,
    node_s1_review,
    node_s1_running,
    node_s2_review,
    node_s2_running,
    node_s3_review,
    node_s3_running,
    node_s4_review,
    node_s4_running,
)

logger = logging.getLogger(__name__)


def _wrap_node(node_fn):
    """
    将接受 (state, user_input) 的节点函数
    包装为 LangGraph 要求的 (state) -> state 形式。
    user_input 通过 state 中的临时字段传递。
    """

    def wrapped(state: ProjectContext) -> ProjectContext:
        user_input = state.pending_input or "开始"
        state.pending_input = ""  # 清空，避免重复执行
        return node_fn(state, user_input)

    return wrapped


def node_complete(state: ProjectContext) -> ProjectContext:
    """终止节点"""
    logger.info(f"[{state.session_id}] Workflow COMPLETE")
    return state


def build_graph():
    """构建并编译 LangGraph 状态机"""

    graph = StateGraph(ProjectContext)

    # ── 注册节点 ──────────────────────────────────────────────────────────────
    graph.add_node("node_init", _wrap_node(node_init))
    graph.add_node("node_s1_running", _wrap_node(node_s1_running))
    graph.add_node("node_s1_review", _wrap_node(node_s1_review))
    graph.add_node("node_s2_running", _wrap_node(node_s2_running))
    graph.add_node("node_s2_review", _wrap_node(node_s2_review))
    graph.add_node("node_s3_running", _wrap_node(node_s3_running))
    graph.add_node("node_s3_review", _wrap_node(node_s3_review))
    graph.add_node("node_s4_running", _wrap_node(node_s4_running))
    graph.add_node("node_s4_review", _wrap_node(node_s4_review))
    graph.add_node("node_complete", node_complete)

    # ── 设置入口 ──────────────────────────────────────────────────────────────
    graph.set_entry_point("node_init")

    # ── 条件路由：每个节点执行完后，根据状态决定下一步 ──────────────────────
    all_nodes = [
        "node_init",
        "node_s1_running",
        "node_s1_review",
        "node_s2_running",
        "node_s2_review",
        "node_s3_running",
        "node_s3_review",
        "node_s4_running",
        "node_s4_review",
    ]

    node_targets = {
        "node_init": "node_init",
        "node_s1_running": "node_s1_running",
        "node_s1_review": "node_s1_review",
        "node_s2_running": "node_s2_running",
        "node_s2_review": "node_s2_review",
        "node_s3_running": "node_s3_running",
        "node_s3_review": "node_s3_review",
        "node_s4_running": "node_s4_running",
        "node_s4_review": "node_s4_review",
        "node_complete": END,
    }

    for node_name in all_nodes:
        graph.add_conditional_edges(
            node_name,
            route_by_state,
            node_targets,
        )

    graph.add_edge("node_complete", END)

    # ── 挂载 PostgreSQL checkpointer ─────────────────────────────────────────
    conn = psycopg.connect(settings.postgres_dsn_sync)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()  # 自动建 checkpoint 相关表

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("LangGraph compiled successfully.")
    return compiled


# 全局图实例（懒加载）
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
