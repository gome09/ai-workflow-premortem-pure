# core/gates/rules/parser_error.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import ProjectContext


class ParserErrorRule:
    """Direct GateRule: parser errors require structured edit repair."""

    rule_id = "parser_error"
    applies_to_stages = {1, 2, 3, 4}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        key = f"stage_{stage}"
        error = ctx.parser_errors.get(key)
        if not error:
            return []

        action_id = readiness._find_pending_action_id(
            ctx, stage, source_type="parser", source_id=key
        )
        blocker = readiness._blocker(
            ctx=ctx,
            stage=stage,
            blocker_type="parser_error",
            severity="high",
            message=f"阶段{stage}存在结构化解析错误，需要提交结构化 edit 动作修复后才能继续。",
            source_type="parser",
            source_id=key,
            action_id=action_id,
            required_resolution="edit_stage_output",
            can_be_overridden_by_approval=False,
            metadata=readiness._with_action_history(
                {
                    "parser_error": error,
                    "requires_structured_output": True,
                    "expected_schema": f"Stage{stage}Schema",
                },
                ctx=ctx,
                stage=stage,
                source_type="parser",
                source_id=key,
                pending_action_id=action_id,
            ),
        )
        return [blocker.model_copy(update={"rule_id": self.rule_id})]


rule = ParserErrorRule()
