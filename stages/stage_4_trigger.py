# stages/stage_4_trigger.py
from __future__ import annotations

import re

from core.config import settings
from core.context_manager import build_stage_context_injection, format_workflow_nodes_for_prompt
from core.models import ProjectContext, Stage4Output, TriggerMethod
from stages.base import BaseStageExecutor
from stages.json_prompts import JSON_OUTPUT_RULES, STAGE_4_JSON_SYSTEM
from stages.prompts import STAGE_4_SYSTEM
from stages.schemas import Stage4Schema
from stages.validators import stage4_schema_to_output


class Stage4Executor(BaseStageExecutor):
    stage_id = 4

    def build_system_prompt(self, ctx: ProjectContext) -> str:
        template = (
            STAGE_4_JSON_SYSTEM if settings.stage_output_mode == "json_first" else STAGE_4_SYSTEM
        )
        return template.format(
            JSON_OUTPUT_RULES=JSON_OUTPUT_RULES,
            context_summary=build_stage_context_injection(ctx, 4),
            workflow_nodes_text=format_workflow_nodes_for_prompt(ctx),
        )

    def parse_output(self, raw_text: str, ctx: ProjectContext) -> ProjectContext:
        if settings.stage_output_mode == "json_first":
            result = self.parse_structured_output(raw_text, ctx)
            if result.parsed:
                schema = Stage4Schema.model_validate(result.parsed)
                ctx.stage_4_output = stage4_schema_to_output(schema, raw_text)
                ctx.parser_errors.pop("stage_4", None)
                return ctx
            ctx.parser_errors["stage_4"] = (
                "Structured output parse failed, fallback to Markdown parser: "
                + "; ".join(result.validation_errors)
            )

        if ctx.stage_4_output is None:
            ctx.stage_4_output = Stage4Output()

        ctx.stage_4_output.raw_summary = raw_text
        node_pattern = re.compile(
            r"### 节点\s*([A-Za-z0-9_-]+)[：:\s]+(.+?)\n"
            r"[\s\S]+?模型/模式[：:]\s*(.+?)\n"
            r"[\s\S]+?入口判断[：:]\s*(.+?)\n"
            r"[\s\S]+?触发指令[：:]\s*([\s\S]+?)(?=\n-\s*执行建议|\n###|\Z)"
            r"(?:[\s\S]+?执行建议[：:]\s*([\s\S]+?))?(?=\n###|\Z)",
            re.IGNORECASE,
        )

        triggers = []
        for match in node_pattern.finditer(raw_text):
            groups = match.groups()
            node_id = groups[0].strip()
            model = groups[2].strip() if groups[2] else ""
            entry_point = groups[3].strip() if groups[3] else ""
            trigger_instr = groups[4].strip() if groups[4] else ""
            exec_suggestion = groups[5].strip() if groups[5] else ""

            triggers.append(
                TriggerMethod(
                    node_id=node_id,
                    model_or_mode=model,
                    entry_point=entry_point,
                    trigger_instruction=trigger_instr,
                    execution_suggestion=exec_suggestion,
                )
            )

        if triggers:
            ctx.stage_4_output.trigger_methods = triggers
            ctx.parser_errors.pop("stage_4", None)
        elif settings.stage_output_mode == "json_first":
            ctx.parser_errors["stage_4"] = "JSON 与 Markdown 解析均未得到 trigger_methods。"

        return ctx
