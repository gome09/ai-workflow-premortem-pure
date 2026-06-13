# core/gates/rules/safety_finding.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import ProjectContext


class SafetyFindingRule:
    """Direct GateRule: high/critical human-review safety findings block advancement."""

    rule_id = "safety_finding"
    applies_to_stages = {1, 2, 3, 4}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        blockers: list[readiness.StageBlocker] = []
        for finding in ctx.safety_findings:
            if finding.stage_id != stage:
                continue
            if finding.status != "open" or not finding.requires_human_review:
                continue
            if finding.severity not in {"high", "critical"}:
                continue
            action_id = readiness._find_pending_action_id(
                ctx, stage, source_type="safety_finding", source_id=finding.finding_id
            )
            blocker = readiness._blocker(
                ctx=ctx,
                stage=stage,
                blocker_type="safety_finding",
                severity=finding.severity,
                message=f"阶段{stage}仍有 {finding.severity} 安全发现未关闭：{finding.finding_id}。",
                source_type="safety_finding",
                source_id=finding.finding_id,
                action_id=action_id,
                required_resolution="resolve_safety_finding"
                if action_id is None
                else "resolve_action",
                can_be_overridden_by_approval=True,
                metadata=readiness._with_action_history(
                    {
                        "risk_type": finding.risk_type,
                        "recommended_action": finding.recommended_action,
                    },
                    ctx=ctx,
                    stage=stage,
                    source_type="safety_finding",
                    source_id=finding.finding_id,
                    pending_action_id=action_id,
                ),
            )
            blockers.append(blocker.model_copy(update={"rule_id": self.rule_id}))
        return blockers


rule = SafetyFindingRule()
