# core/gates/rules/stage3_eval_failure.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.gates.risk_profile import ProjectGateRiskTier, build_stage3_gate_profile
from core.models import ProjectContext


def _risk_adjusted_high_risk_nodes(ctx: ProjectContext, tier: ProjectGateRiskTier) -> set[str]:
    """Return workflow node IDs that require eval coverage under the given risk tier.

    - LOW: only nodes addressing *critical* failure modes.
    - MEDIUM: nodes addressing *high* or *critical* failure modes (same as default).
    - HIGH / CRITICAL: same as default.
    """
    if not ctx.stage_1_output or not ctx.stage_2_output:
        return set()

    if tier == ProjectGateRiskTier.LOW:
        severity_filter = {"critical"}
    else:
        severity_filter = {"high", "critical"}

    high_risk_failure_modes = {
        fm.id
        for fm in ctx.stage_1_output.failure_modes
        if str(fm.severity).lower() in severity_filter
    }
    return {
        node.node_id
        for node in ctx.stage_2_output.workflow_nodes
        if high_risk_failure_modes.intersection(set(node.failure_modes_addressed or []))
    }


class Stage3EvalFailureRule:
    """Direct GateRule: high-risk workflow nodes require EvalCase coverage and failure handling.

    Risk-adaptive: low-risk projects only require eval coverage for nodes addressing
    *critical* failure modes, not all high-severity nodes.
    """

    rule_id = "stage3_eval_failure"
    applies_to_stages = {3}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 3:
            return []

        profile = build_stage3_gate_profile(ctx)
        high_risk_nodes = _risk_adjusted_high_risk_nodes(ctx, profile.risk_tier)
        if not high_risk_nodes:
            return []

        blockers: list[readiness.StageBlocker] = []
        eval_case_nodes = {case.target_node_id for case in ctx.eval_cases if case.target_node_id}

        for node_id in sorted(high_risk_nodes - eval_case_nodes):
            action_id = readiness._find_pending_action_id(
                ctx, 3, source_type="eval_coverage", source_id=node_id
            )
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=3,
                    blocker_type="eval_failure",
                    severity="high",
                    message=f"阶段3高风险节点 {node_id} 缺少 EvalCase 覆盖，不能仅作为提醒放行。",
                    source_type="eval_coverage",
                    source_id=node_id,
                    action_id=action_id,
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata=readiness._with_action_history(
                        {
                            "target_node_id": node_id,
                            "gap_type": "missing_eval_case_coverage",
                            "expected_schema": "Stage3Schema",
                            "requires_structured_output": True,
                        },
                        ctx=ctx,
                        stage=3,
                        source_type="eval_coverage",
                        source_id=node_id,
                        pending_action_id=action_id,
                    ),
                )
            )

        for case in ctx.eval_cases:
            if case.passed is not False or case.target_node_id not in high_risk_nodes:
                continue
            if readiness._has_resolved_source_action(
                ctx,
                3,
                source_type="eval_case",
                source_id=case.eval_id,
                decisions={"approve", "edit"},
            ):
                continue
            action_id = readiness._find_pending_action_id(
                ctx, 3, source_type="eval_case", source_id=case.eval_id
            )
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=3,
                    blocker_type="eval_failure",
                    severity="high",
                    message=f"阶段3高风险节点 {case.target_node_id} 的 EvalCase {case.eval_id} 失败且未处理。",
                    source_type="eval_case",
                    source_id=case.eval_id,
                    action_id=action_id,
                    required_resolution="resolve_action",
                    can_be_overridden_by_approval=True,
                    metadata=readiness._with_action_history(
                        {
                            "target_node_id": case.target_node_id,
                            "scenario_type": case.scenario_type,
                        },
                        ctx=ctx,
                        stage=3,
                        source_type="eval_case",
                        source_id=case.eval_id,
                        pending_action_id=action_id,
                    ),
                )
            )

        for run in ctx.eval_runs:
            failed = run.status == "failed" or run.judge_result == "failed"
            needs_review = run.judge_result == "needs_review"
            if not (failed or needs_review) or run.target_node_id not in high_risk_nodes:
                continue
            if readiness._has_resolved_source_action(
                ctx,
                3,
                source_type="eval_run",
                source_id=run.run_id,
                decisions={"approve", "edit"},
            ):
                continue
            action_id = readiness._find_pending_action_id(
                ctx, 3, source_type="eval_run", source_id=run.run_id
            )
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=3,
                    blocker_type="eval_failure",
                    severity="high",
                    message=(
                        f"阶段3高风险节点 {run.target_node_id} 的 EvalRun {run.run_id} "
                        f"{'需要人工复核' if needs_review and not failed else '失败'}且未处理。"
                    ),
                    source_type="eval_run",
                    source_id=run.run_id,
                    action_id=action_id,
                    required_resolution="resolve_action",
                    can_be_overridden_by_approval=True,
                    metadata=readiness._with_action_history(
                        {
                            "target_node_id": run.target_node_id,
                            "judge_result": run.judge_result,
                            "status": run.status,
                            "review_required": bool(needs_review and not failed),
                        },
                        ctx=ctx,
                        stage=3,
                        source_type="eval_run",
                        source_id=run.run_id,
                        pending_action_id=action_id,
                    ),
                )
            )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = Stage3EvalFailureRule()
