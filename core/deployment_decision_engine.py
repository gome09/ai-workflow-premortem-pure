# core/deployment_decision_engine.py
"""Stage 4 部署决策引擎。

基于确定性规则生成部署决策建议。此引擎生成的决策会覆盖 LLM 自报决策，
最终一致性由 CrossStageIntegrityRule 校验。
"""

from __future__ import annotations

from core.models import DeploymentDecision, ProjectContext


def _count_open_safety_findings(ctx: ProjectContext, severity: str) -> int:
    return sum(1 for f in ctx.safety_findings if f.severity == severity and f.status == "open")


def _has_failed_evals(ctx: ProjectContext) -> bool:
    return any(run.judge_result == "failed" for run in ctx.eval_runs)


def _has_pending_expert_review(ctx: ProjectContext) -> bool:
    """检查是否有待处理的专家审核。"""
    for action in ctx.get_pending_actions():
        if action.action_type == "escalate" and action.blocking:
            return True
    return False


def _collect_unresolved_risk_ids(ctx: ProjectContext) -> list[str]:
    """收集未关闭的风险 ID。"""
    ids: list[str] = []
    for f in ctx.safety_findings:
        if f.status == "open":
            ids.append(f.finding_id)
    # 也包含未覆盖的 high/critical failure mode
    if ctx.stage_1_output:
        high_risk_fms = {
            fm.id
            for fm in ctx.stage_1_output.failure_modes
            if str(fm.severity).lower() in {"high", "critical"}
        }
        if ctx.stage_2_output:
            covered = set()
            for node in ctx.stage_2_output.workflow_nodes:
                covered.update(node.failure_modes_addressed or [])
            for fm_id in sorted(high_risk_fms - covered):
                ids.append(fm_id)
    return ids


def generate_deployment_decision(ctx: ProjectContext) -> DeploymentDecision:
    """基于确定性规则生成部署决策建议。

    决策逻辑：
    1. 存在未关闭 critical 风险或失败评测 → no_go
    2. 存在未解决 high 风险、阻断动作或专家审核 → conditional_go
    3. 全部门禁通过 → pilot_only（Demo 默认保守）

    is_demo_recommendation 始终为 True。
    """
    open_critical = _count_open_safety_findings(ctx, "critical")
    open_high = _count_open_safety_findings(ctx, "high")
    failed_evals = _has_failed_evals(ctx)
    blocking_actions = ctx.has_blocking_actions()
    expert_review_pending = _has_pending_expert_review(ctx)
    unresolved_risk_ids = _collect_unresolved_risk_ids(ctx)

    if open_critical > 0 or failed_evals:
        return DeploymentDecision(
            decision="no_go",
            decision_scope="deployment_paused",
            decision_rationale=(
                f"存在 {open_critical} 个未关闭 critical 风险"
                + ("和失败评测" if failed_evals else "")
                + "，不建议部署。"
            ),
            unresolved_risk_ids=unresolved_risk_ids,
            required_conditions=[],
            required_approvals=["授权安全负责人"],
            monitoring_requirements=[],
            rollback_conditions=["立即停止试点", "回滚到上一稳定版本"],
            prohibited_uses=["不得用于任何生产场景"],
            review_after="风险关闭后重新评估",
            human_accountable_role="项目负责人 + 安全负责人",
            is_demo_recommendation=True,
        )

    if open_high > 0 or blocking_actions or expert_review_pending:
        conditions: list[str] = []
        if open_high > 0:
            conditions.append(f"关闭所有 {open_high} 个未解决 high 风险")
        if blocking_actions:
            conditions.append("解决所有阻断型人工动作")
        if expert_review_pending:
            conditions.append("完成专家审核")
        conditions.append("通过完整评测验证")
        conditions.append("配置监控和告警机制")

        return DeploymentDecision(
            decision="conditional_go",
            decision_scope="conditional_deployment",
            decision_rationale=("存在未解决问题，需满足前置条件后方可受限部署。"),
            unresolved_risk_ids=unresolved_risk_ids,
            required_conditions=conditions,
            required_approvals=["项目负责人", "安全负责人"],
            monitoring_requirements=[
                "实时监控输出质量指标",
                "每周审核人工审核积压",
                "设置 SLA 告警阈值",
            ],
            rollback_conditions=[
                "评测通过率低于基线 10%",
                "出现 critical 安全发现",
                "人工审核积压超过 48 小时",
            ],
            prohibited_uses=["不得用于高风险自动决策场景"],
            review_after="每月或在重大变更后复审",
            human_accountable_role="项目负责人",
            is_demo_recommendation=True,
        )

    # 全部门禁通过 → pilot_only（Demo 默认保守）
    return DeploymentDecision(
        decision="pilot_only",
        decision_scope="limited_pilot",
        decision_rationale="所有门禁已通过，建议在小范围内受限试点。",
        unresolved_risk_ids=unresolved_risk_ids,
        required_conditions=["完成试点范围确认", "配置试点监控"],
        required_approvals=["项目负责人"],
        monitoring_requirements=[
            "试点期间每日审核关键指标",
            "设置试点停止条件触发告警",
        ],
        rollback_conditions=[
            "试点期间出现任何 critical 安全发现",
            "用户投诉率超过预期阈值",
            "评测通过率下降超过 5%",
        ],
        prohibited_uses=["不得超出试点范围", "不得用于高影响自动决策"],
        review_after="试点结束后评估是否扩大部署范围",
        human_accountable_role="项目负责人",
        is_demo_recommendation=True,
    )


def apply_deployment_decision(ctx: ProjectContext) -> DeploymentDecision | None:
    """为 Stage 4 生成并设置部署决策。

    如果 ctx 没有 stage_4_output 则不做操作。
    """
    if not ctx.stage_4_output:
        return None
    decision = generate_deployment_decision(ctx)
    ctx.stage_4_output.deployment_decision = decision
    return decision
