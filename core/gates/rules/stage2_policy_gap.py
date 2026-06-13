# core/gates/rules/stage2_policy_gap.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import ProjectContext


class Stage2PolicyGapRule:
    """Direct GateRule: high/critical failure modes must be covered by Stage 2 policy."""

    rule_id = "stage2_policy_gap"
    applies_to_stages = {2}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 2 or not ctx.stage_1_output or not ctx.stage_2_output:
            return []

        high_risk_ids = {
            fm.id
            for fm in ctx.stage_1_output.failure_modes
            if str(fm.severity).lower() in {"high", "critical"}
        }
        if not high_risk_ids:
            return []

        severity_by_fm = {
            fm.id: fm.severity
            for fm in ctx.stage_1_output.failure_modes
            if str(fm.severity).lower() in {"high", "critical"}
        }
        covered: set[str] = set()
        blockers: list[readiness.StageBlocker] = []

        for node in ctx.stage_2_output.workflow_nodes:
            addressed = set(node.failure_modes_addressed or [])
            high_risk_addressed = addressed.intersection(high_risk_ids)
            covered.update(high_risk_addressed)
            if high_risk_addressed and node.oversight_policy is None:
                action_id = readiness._find_pending_action_id(
                    ctx, 2, source_type="policy_gap", source_id=node.node_id
                )
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=2,
                        blocker_type="policy_gap",
                        severity="high",
                        message=(
                            f"阶段2节点 {node.node_id} 覆盖高风险 failure_mode "
                            f"{', '.join(sorted(high_risk_addressed))}，但缺少 HumanOversightPolicy。"
                        ),
                        source_type="workflow_node",
                        source_id=node.node_id,
                        action_id=action_id,
                        required_resolution="edit_stage_output",
                        can_be_overridden_by_approval=False,
                        metadata=readiness._with_action_history(
                            {
                                "failure_mode_ids": sorted(high_risk_addressed),
                                "requires_structured_output": True,
                                "expected_schema": "Stage2Schema",
                            },
                            ctx=ctx,
                            stage=2,
                            source_type="policy_gap",
                            source_id=node.node_id,
                            pending_action_id=action_id,
                        ),
                    )
                )

        for failure_mode_id in sorted(high_risk_ids - covered):
            action_id = readiness._find_pending_action_id(
                ctx, 2, source_type="policy_gap", source_id=failure_mode_id
            )
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=2,
                    blocker_type="policy_gap",
                    severity=severity_by_fm.get(failure_mode_id, "high"),
                    message=f"阶段2没有 workflow node 覆盖高风险 failure_mode：{failure_mode_id}。",
                    source_type="failure_mode",
                    source_id=failure_mode_id,
                    action_id=action_id,
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata=readiness._with_action_history(
                        {
                            "gap_type": "uncovered_high_risk_failure_mode",
                            "requires_structured_output": True,
                            "expected_schema": "Stage2Schema",
                        },
                        ctx=ctx,
                        stage=2,
                        source_type="policy_gap",
                        source_id=failure_mode_id,
                        pending_action_id=action_id,
                    ),
                )
            )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = Stage2PolicyGapRule()
