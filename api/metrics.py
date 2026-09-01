"""Custom business metrics for Prometheus (spec §4.3 / T3.5).

注册在现有 prometheus_fastapi_instrumentator 之上；prometheus_client 默认 REGISTRY
的指标会被 instrumentator 的 `/metrics` 端点一并暴露。

基数控制：
- tenant 标签用名称非 UUID；
- 不加 session_id 级标签（避免无界基数）。

所有打点函数失败不阻断主路径——调用方已用 try/except 包裹。
"""

from __future__ import annotations

import logging

from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# 会话状态（Gauge，按需刷新）
# ─────────────────────────────────────────────────────────
premortem_sessions_total = Gauge(
    "premortem_sessions_total",
    "Total sessions by tenant and state",
    ["tenant", "state"],
)

# ─────────────────────────────────────────────────────────
# 门禁评估（Counter，评估路径打点）
# ─────────────────────────────────────────────────────────
premortem_gate_evaluations_total = Counter(
    "premortem_gate_evaluations_total",
    "Gate evaluations by result",
    ["result"],  # passed | blocked
)

premortem_gate_blocked_total = Counter(
    "premortem_gate_blocked_total",
    "Gate blocks by rule_id",
    ["rule_id"],
)

# ─────────────────────────────────────────────────────────
# 待处理动作（Gauge）
# ─────────────────────────────────────────────────────────
premortem_pending_actions = Gauge(
    "premortem_pending_actions",
    "Pending human actions by risk level",
    ["risk_level"],
)

# ─────────────────────────────────────────────────────────
# LLM 用量（Counter，与阶段 2 LLM10 共用数据源）
# ─────────────────────────────────────────────────────────
premortem_llm_calls_total = Counter(
    "premortem_llm_calls_total",
    "LLM calls total",
)

premortem_llm_tokens_total = Counter(
    "premortem_llm_tokens_total",
    "LLM tokens total (input+output)",
)


def record_gate_evaluation_metrics(passed: bool, blocking_rule_ids: list[str]) -> None:
    """评估路径打点——在 engine._try_persist_gate_evaluation 内调用。"""
    premortem_gate_evaluations_total.labels(result="passed" if passed else "blocked").inc()
    if not passed:
        for rid in blocking_rule_ids:
            premortem_gate_blocked_total.labels(rule_id=rid).inc()


def record_llm_usage(call_count_delta: int = 1, token_delta: int = 0) -> None:
    """LLM 用量打点——在 execution_service.execute_one_turn 内调用。"""
    if call_count_delta:
        premortem_llm_calls_total.inc(call_count_delta)
    if token_delta:
        premortem_llm_tokens_total.inc(token_delta)


def refresh_gauge_metrics(tenant_name: str = "default") -> None:
    """按需刷新 Gauge 指标（会话状态分布、待处理人工动作分布）。

    2026-09-01 修复（STATE.md Blockers 登记项）：
    - 语义修正：`premortem_pending_actions` 此前被喂了会话风险档位分布
      （`risk_tier_distribution`），语义错配；现改为真实的 pending 动作
      按 risk_level 计数（`governance_metrics_all_tenants`）。
    - 数据修正：此前调用 `governance_overview(tenant_id="")` 恒返回零值
      模板；Prometheus Gauge 是进程级全局指标且刷新点（lifespan 启动）
      无请求上下文，现改为跨租户真实聚合。
    失败不影响主路径。
    """
    try:
        from storage.session_store import session_store

        metrics_data = session_store.governance_metrics_all_tenants()
        for state, cnt in metrics_data.get("state_distribution", {}).items():
            premortem_sessions_total.labels(tenant=tenant_name, state=state).set(cnt)
        for risk, cnt in metrics_data.get("pending_actions_by_risk", {}).items():
            premortem_pending_actions.labels(risk_level=risk).set(cnt)
    except Exception:
        logger.debug("refresh_gauge_metrics failed; non-fatal", exc_info=True)
