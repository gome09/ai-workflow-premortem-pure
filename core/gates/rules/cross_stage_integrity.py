# core/gates/rules/cross_stage_integrity.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import ProjectContext


class CrossStageIntegrityRule:
    """跨阶段 ID 引用完整性和覆盖校验。

    校验 Stage 2→1、Stage 3→1/2、Stage 4 的 ID 引用一致性，
    以及 high/critical failure mode 的覆盖完整性。
    """

    rule_id = "cross_stage_integrity"
    applies_to_stages = {2, 3, 4}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        blockers: list[readiness.StageBlocker] = []
        if stage >= 2:
            blockers += self._check_stage2_references(ctx)
        if stage >= 3:
            blockers += self._check_stage3_references(ctx)
            blockers += self._check_high_risk_test_coverage(ctx)
        if stage >= 4:
            blockers += self._check_stage4_decision(ctx)
        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]

    def _check_stage2_references(self, ctx: ProjectContext) -> list[readiness.StageBlocker]:
        """Stage 2 引用的 failure_mode_id 必须存在于 Stage 1。"""
        blockers = []
        if not ctx.stage_1_output or not ctx.stage_2_output:
            return blockers
        valid_fm_ids = {fm.id for fm in ctx.stage_1_output.failure_modes}
        for node in ctx.stage_2_output.workflow_nodes:
            for fm_id in node.failure_modes_addressed or []:
                if fm_id not in valid_fm_ids:
                    blockers.append(
                        readiness._blocker(
                            ctx=ctx,
                            stage=2,
                            blocker_type="cross_stage_integrity",
                            severity="high",
                            message=f"阶段2节点 {node.node_id} 引用了不存在的 failure_mode_id：{fm_id}。",
                            source_type="workflow_node",
                            source_id=node.node_id,
                            required_resolution="edit_stage_output",
                            can_be_overridden_by_approval=False,
                            metadata={"invalid_reference": fm_id, "stage": 2},
                        )
                    )
        return blockers

    def _check_stage3_references(self, ctx: ProjectContext) -> list[readiness.StageBlocker]:
        """Stage 3 引用的 failure_mode_id 和 node_id 必须存在。"""
        blockers = []
        if not ctx.stage_1_output or not ctx.stage_2_output or not ctx.stage_3_output:
            return blockers
        valid_fm_ids = {fm.id for fm in ctx.stage_1_output.failure_modes}
        valid_node_ids = {node.node_id for node in ctx.stage_2_output.workflow_nodes}
        for result in ctx.stage_3_output.test_results:
            fm_id = getattr(result, "failure_mode_id", "")
            node_id = result.tested_node_id
            if fm_id and fm_id not in valid_fm_ids:
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=3,
                        blocker_type="cross_stage_integrity",
                        severity="high",
                        message=f"阶段3测试结果引用了不存在的 failure_mode_id：{fm_id}。",
                        source_type="stress_test",
                        source_id=getattr(result, "case_id", node_id),
                        required_resolution="edit_stage_output",
                        can_be_overridden_by_approval=False,
                        metadata={"invalid_reference": fm_id, "stage": 3},
                    )
                )
            if node_id and node_id not in valid_node_ids:
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=3,
                        blocker_type="cross_stage_integrity",
                        severity="high",
                        message=f"阶段3测试结果引用了不存在的 node_id：{node_id}。",
                        source_type="stress_test",
                        source_id=getattr(result, "case_id", node_id),
                        required_resolution="edit_stage_output",
                        can_be_overridden_by_approval=False,
                        metadata={"invalid_reference": node_id, "stage": 3},
                    )
                )
        return blockers

    def _check_high_risk_test_coverage(self, ctx: ProjectContext) -> list[readiness.StageBlocker]:
        """所有 high/critical failure mode 必须至少有一个测试。"""
        blockers = []
        if not ctx.stage_1_output or not ctx.stage_3_output:
            return blockers
        high_risk_fms = {
            fm.id
            for fm in ctx.stage_1_output.failure_modes
            if str(fm.severity).lower() in {"high", "critical"}
        }
        tested_fm_ids = {
            getattr(r, "failure_mode_id", "")
            for r in ctx.stage_3_output.test_results
            if getattr(r, "failure_mode_id", "")
        }
        for fm_id in sorted(high_risk_fms - tested_fm_ids):
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=3,
                    blocker_type="cross_stage_integrity",
                    severity="high",
                    message=f"高风险 failure_mode {fm_id} 没有对应的测试用例覆盖。",
                    source_type="failure_mode",
                    source_id=fm_id,
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "untested_high_risk_failure_mode", "stage": 3},
                )
            )
        return blockers

    def _check_stage4_decision(self, ctx: ProjectContext) -> list[readiness.StageBlocker]:
        """Stage 4 部署决策一致性校验。"""
        blockers = []
        if not ctx.stage_4_output:
            return blockers
        decision = ctx.stage_4_output.deployment_decision
        if decision is None:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="cross_stage_integrity",
                    severity="critical",
                    message="阶段4缺少部署决策结构（deployment_decision）。",
                    source_type="stage_output",
                    source_id="stage_4",
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "missing_deployment_decision"},
                )
            )
            return blockers

        # 统计未关闭风险
        open_critical = sum(
            1 for f in ctx.safety_findings if f.severity == "critical" and f.status == "open"
        )
        open_high = sum(
            1 for f in ctx.safety_findings if f.severity == "high" and f.status == "open"
        )
        has_failed_evals = any(run.judge_result == "failed" for run in ctx.eval_runs)
        has_blocking_actions = ctx.has_blocking_actions()

        # 存在未关闭 critical 风险时不得 go
        if open_critical > 0 and decision.decision == "go":
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="cross_stage_integrity",
                    severity="critical",
                    message=f"存在 {open_critical} 个未关闭的 critical 风险，不得给出 go 决策。",
                    source_type="safety_finding",
                    source_id="critical_open",
                    required_resolution="resolve_safety_finding",
                    can_be_overridden_by_approval=False,
                    metadata={"decision_conflict": "critical_open_risk_vs_go"},
                )
            )

        # 存在未解决 high 风险、失败评测或阻断动作时不得无条件 go
        if (
            open_high > 0 or has_failed_evals or has_blocking_actions
        ) and decision.decision == "go":
            reasons = []
            if open_high > 0:
                reasons.append(f"{open_high} 个未关闭 high 风险")
            if has_failed_evals:
                reasons.append("存在失败评测")
            if has_blocking_actions:
                reasons.append("存在阻断型人工动作")
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="cross_stage_integrity",
                    severity="critical",
                    message=f"存在 {'、'.join(reasons)}，不得给出无条件 go 决策。",
                    source_type="stage_output",
                    source_id="decision_conflict",
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata={"decision_conflict": "unresolved_issues_vs_go"},
                )
            )

        # conditional_go 必须有 required_conditions
        if decision.decision == "conditional_go" and not decision.required_conditions:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="cross_stage_integrity",
                    severity="high",
                    message="conditional_go 决策必须列出可验证的前置条件（required_conditions）。",
                    source_type="stage_output",
                    source_id="missing_conditions",
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "conditional_go_without_conditions"},
                )
            )

        # pilot_only 必须有 rollback_conditions
        if decision.decision == "pilot_only" and not decision.rollback_conditions:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="cross_stage_integrity",
                    severity="high",
                    message="pilot_only 决策必须明确停止/回滚条件（rollback_conditions）。",
                    source_type="stage_output",
                    source_id="missing_rollback",
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "pilot_only_without_rollback"},
                )
            )

        return blockers


rule = CrossStageIntegrityRule()
