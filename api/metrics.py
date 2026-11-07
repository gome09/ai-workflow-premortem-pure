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

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# 数据库操作耗时（Histogram，存储层打点）
# ─────────────────────────────────────────────────────────
premortem_db_operation_seconds = Histogram(
    "premortem_db_operation_seconds",
    "Session-store operation latency in seconds",
    ["operation"],  # save | load | list | governance
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def observe_db_operation(operation: str, elapsed_seconds: float) -> None:
    """存储层打点——由 storage 后端在操作完成后调用，失败不阻断主路径。"""
    try:
        premortem_db_operation_seconds.labels(operation=operation).observe(elapsed_seconds)
    except Exception:  # pragma: no cover - metrics must never break the request path
        logger.debug("observe_db_operation failed; non-fatal", exc_info=True)


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

# ─────────────────────────────────────────────────────────
# 模型调用失败与结构化输出（可靠性观测）
# ─────────────────────────────────────────────────────────
premortem_llm_failures_total = Counter(
    "premortem_llm_failures_total",
    "LLM call failures by stage and fixed error code",
    ["stage", "error_code"],  # timeout | rate_limit | auth | connection | server_error | ...
)

premortem_structured_output_failures_total = Counter(
    "premortem_structured_output_failures_total",
    "Structured output parse failures by stage and parser status",
    ["stage", "status"],  # non_json | validation_failed | failed | ...
)

# ─────────────────────────────────────────────────────────
# 真实目标执行（target_http）
# ─────────────────────────────────────────────────────────
premortem_target_executions_total = Counter(
    "premortem_target_executions_total",
    "Real target executions by outcome",
    ["outcome"],  # success | failed | timeout | error
)

# ─────────────────────────────────────────────────────────
# 数据留存清理
# ─────────────────────────────────────────────────────────
premortem_retention_sessions_purged_total = Counter(
    "premortem_retention_sessions_purged_total",
    "Sessions purged by the retention executor",
)

premortem_retention_audit_rows_purged_total = Counter(
    "premortem_retention_audit_rows_purged_total",
    "Audit rows purged by the retention executor",
    ["source"],  # live | archive
)

premortem_retention_errors_total = Counter(
    "premortem_retention_errors_total",
    "Retention sweep errors (purge or checkpoint cleanup)",
)

# ─────────────────────────────────────────────────────────
# 上线审批决策
# ─────────────────────────────────────────────────────────
premortem_release_approvals_total = Counter(
    "premortem_release_approvals_total",
    "Release approval decisions",
    ["decision"],  # granted | rejected | denied
)

# ─────────────────────────────────────────────────────────
# 发布门禁检查（Counter，机器调用）
# ─────────────────────────────────────────────────────────
premortem_release_gate_checks_total = Counter(
    "premortem_release_gate_checks_total",
    "Release gate checks by decision and fixed reason code",
    ["decision", "reason_code"],
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


def record_llm_failure(stage: int | None, error_code: str) -> None:
    """模型调用失败打点——由 core.llm.errors 统一调用，失败不阻断主路径。"""
    try:
        premortem_llm_failures_total.labels(
            stage=str(stage) if stage is not None else "unknown",
            error_code=error_code,
        ).inc()
    except Exception:  # pragma: no cover - metrics must never break the error path
        logger.debug("record_llm_failure failed; non-fatal", exc_info=True)


def record_structured_output_failure(stage: int, status: str) -> None:
    """结构化输出解析失败打点——由 BaseStageExecutor.parse_structured_output 调用。"""
    try:
        premortem_structured_output_failures_total.labels(stage=str(stage), status=status).inc()
    except Exception:  # pragma: no cover
        logger.debug("record_structured_output_failure failed; non-fatal", exc_info=True)


def record_target_execution(outcome: str) -> None:
    """真实目标执行打点——由 eval_runner 在 target_http 分支调用。"""
    try:
        premortem_target_executions_total.labels(outcome=outcome).inc()
    except Exception:  # pragma: no cover
        logger.debug("record_target_execution failed; non-fatal", exc_info=True)


def record_retention_cycle(result: dict) -> None:
    """留存清理统计打点——会话/审计删除量与错误数。"""
    try:
        premortem_retention_sessions_purged_total.inc(int(result.get("sessions_purged", 0) or 0))
        premortem_retention_audit_rows_purged_total.labels(source="live").inc(
            int(result.get("audit_events_deleted", 0) or 0)
        )
        premortem_retention_audit_rows_purged_total.labels(source="archive").inc(
            int(result.get("archived_events_deleted", 0) or 0)
        )
        premortem_retention_errors_total.inc(
            int(result.get("errors_count", len(result.get("errors", []) or [])) or 0)
        )
    except Exception:  # pragma: no cover
        logger.debug("record_retention_cycle failed; non-fatal", exc_info=True)


def record_release_approval(decision: str) -> None:
    """上线审批决策打点——granted / rejected / denied。"""
    try:
        premortem_release_approvals_total.labels(decision=decision).inc()
    except Exception:  # pragma: no cover
        logger.debug("record_release_approval failed; non-fatal", exc_info=True)


def record_release_gate_check(decision: str, reason_code: str) -> None:
    """发布门禁检查打点——decision=allow|block + 固定 reason_code。"""
    try:
        premortem_release_gate_checks_total.labels(
            decision=decision,
            reason_code=reason_code,
        ).inc()
    except Exception:  # pragma: no cover
        logger.debug("record_release_gate_check failed; non-fatal", exc_info=True)


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
