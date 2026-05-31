# core/gates/rules/stage4_final_governance.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import ProjectContext


class Stage4FinalGovernanceRule:
    """Direct GateRule: Stage 4 cannot complete while upstream hard governance gaps remain."""

    rule_id = "stage4_final_governance"
    applies_to_stages = {4}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 4:
            return []

        blockers: list[readiness.StageBlocker] = []

        for upstream_stage in range(1, 4):
            upstream = readiness.evaluate_stage_gate(ctx, upstream_stage)
            for blocker in upstream.blockers:
                if (
                    blocker.blocker_type == "missing_stage_output"
                    and not readiness.is_stage_actionable(ctx, upstream_stage)
                ):
                    continue
                if blocker.can_be_overridden_by_approval:
                    continue
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=4,
                        blocker_type="final_governance",
                        severity=blocker.severity,
                        message=f"流程完成前上游阶段{upstream_stage}仍有未关闭治理项：{blocker.message}",
                        source_type=blocker.source_type,
                        source_id=blocker.source_id or blocker.blocker_id,
                        action_id=blocker.action_id,
                        required_resolution=blocker.required_resolution,
                        can_be_overridden_by_approval=False,
                        metadata={
                            "upstream_stage_id": upstream_stage,
                            "upstream_blocker_id": blocker.blocker_id,
                            "upstream_blocker_type": blocker.blocker_type,
                            "upstream_required_resolution": blocker.required_resolution,
                            "upstream_metadata": blocker.metadata,
                        },
                    )
                )

        for finding in ctx.safety_findings:
            if finding.status == "open" and finding.severity in {"high", "critical"}:
                action_id = None
                if finding.stage_id is not None:
                    action_id = readiness._find_pending_action_id(
                        ctx,
                        finding.stage_id,
                        source_type="safety_finding",
                        source_id=finding.finding_id,
                    )
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=4,
                        blocker_type="final_governance",
                        severity=finding.severity,
                        message=f"流程完成前仍有 {finding.severity} 安全发现未关闭：{finding.finding_id}。",
                        source_type="safety_finding",
                        source_id=finding.finding_id,
                        action_id=action_id,
                        required_resolution="resolve_action"
                        if action_id
                        else "resolve_safety_finding",
                        can_be_overridden_by_approval=finding.severity != "critical",
                        metadata={"risk_type": finding.risk_type, "stage_id": finding.stage_id},
                    )
                )

        for key, value in ctx.parser_errors.items():
            if key.startswith("stage_") and value:
                stage_token = key.split("_", 1)[-1]
                source_stage = int(stage_token) if stage_token.isdigit() else 4
                action_id = readiness._find_pending_action_id(
                    ctx, source_stage, source_type="parser", source_id=key
                )
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=4,
                        blocker_type="final_governance",
                        severity="high",
                        message=f"流程完成前仍有 parser error 未关闭：{key}。",
                        source_type="parser",
                        source_id=key,
                        action_id=action_id,
                        required_resolution="edit_stage_output",
                        can_be_overridden_by_approval=False,
                        metadata={
                            "parser_error": value,
                            "requires_structured_output": True,
                            "expected_schema": f"Stage{source_stage}Schema",
                        },
                    )
                )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = Stage4FinalGovernanceRule()
