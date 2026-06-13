# core/gates/rules/missing_output.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import ProjectContext


class MissingOutputRule:
    """Direct GateRule: block advancement until the current stage has output."""

    rule_id = "missing_output"
    applies_to_stages = {1, 2, 3, 4}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if readiness._stage_output_exists(ctx, stage):
            return []
        blocker = readiness._blocker(
            ctx=ctx,
            stage=stage,
            blocker_type="missing_stage_output",
            severity="medium",
            message=f"阶段{stage}尚未生成结构化输出，不能进入下一阶段。",
            source_type="stage",
            source_id=readiness._stage_key(stage),
            required_resolution="run_stage",
            can_be_overridden_by_approval=False,
        )
        return [blocker.model_copy(update={"rule_id": self.rule_id})]


rule = MissingOutputRule()
