# graph/runner.py
from __future__ import annotations

import logging
from collections.abc import Callable

from core.models import ProjectContext, SessionState
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

NodeFn = Callable[[ProjectContext, str], ProjectContext]


NODE_BY_STATE: dict[SessionState, NodeFn] = {
    SessionState.INIT: node_init,
    SessionState.S1_RUNNING: node_s1_running,
    SessionState.S1_REVIEW: node_s1_review,
    SessionState.S2_RUNNING: node_s2_running,
    SessionState.S2_REVIEW: node_s2_review,
    SessionState.S3_RUNNING: node_s3_running,
    SessionState.S3_REVIEW: node_s3_review,
    SessionState.S4_RUNNING: node_s4_running,
    SessionState.S4_REVIEW: node_s4_review,
}


def run_one_step(ctx: ProjectContext) -> ProjectContext:
    """
    按当前 ProjectContext.current_state 只推进一个节点。

    原 graph.invoke() 会沿条件边持续执行到 END 或递归上限，不符合
    "用户发一条消息 -> 状态机推进一步 -> 等用户审核/确认"的交互模型。
    这里保留 graph/nodes.py 中已有节点实现，但显式做单步调度。

    # TODO: 这里其实可以用 LangGraph 的 interrupt_before 来实现暂停,
    # 但当时调 interrupt 模式调了半天没调通, 就先用 single_step 了
    """
    if ctx.current_state == SessionState.COMPLETE:
        logger.info("[%s] Workflow already COMPLETE; no node executed.", ctx.session_id)
        ctx.pending_input = ""
        return ctx

    node_fn = NODE_BY_STATE.get(ctx.current_state)
    if node_fn is None:
        logger.warning(
            "[%s] Unknown state %s; fallback to INIT node.",
            ctx.session_id,
            ctx.current_state,
        )
        node_fn = node_init

    user_input = ctx.pending_input or "开始"
    ctx.pending_input = ""  # 避免同一轮输入被重复执行

    return node_fn(ctx, user_input)
