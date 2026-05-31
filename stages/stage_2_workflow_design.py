# stages/stage_2_workflow_design.py
from __future__ import annotations

import re

from core.config import settings
from core.context_manager import (
    build_stage_context_injection,
    format_failure_modes_for_prompt,
)
from core.models import HumanOversightPolicy, ProjectContext, Stage2Output, WorkflowNode
from stages.base import BaseStageExecutor
from stages.json_prompts import JSON_OUTPUT_RULES, STAGE_2_JSON_SYSTEM
from stages.prompts import STAGE_2_SYSTEM
from stages.schemas import Stage2Schema
from stages.validators import stage2_schema_to_output


def infer_oversight_policy(node: WorkflowNode) -> HumanOversightPolicy | None:
    """旧 Markdown 输出下，基于人工动作/检查标准轻量推断监督策略。

    Always returns a policy — even for nodes whose text does not contain
    explicit supervision keywords.  A lightweight default policy is better
    than None, which would block the gate for any high-severity failure mode
    the node addresses.
    """
    text = f"{node.human_action} {node.check_criteria}"

    required_action = (
        "verify_evidence"
        if any(keyword in text for keyword in ["证据", "核验", "来源"])
        else "approve"
    )
    risk_level = (
        "high"
        if any(keyword in text for keyword in ["高风险", "严重", "关键", "专家"])
        else "medium"
    )
    return HumanOversightPolicy(
        stage_id=2,
        risk_level=risk_level,
        trigger_reason=f"节点 {node.node_id} 的工作流步骤需要监督确认",
        required_action=required_action,
        evidence_required=required_action == "verify_evidence",
        can_auto_continue=False,
    )


class Stage2Executor(BaseStageExecutor):
    stage_id = 2

    def build_system_prompt(self, ctx: ProjectContext) -> str:
        template = (
            STAGE_2_JSON_SYSTEM if settings.stage_output_mode == "json_first" else STAGE_2_SYSTEM
        )
        return template.format(
            JSON_OUTPUT_RULES=JSON_OUTPUT_RULES,
            context_summary=build_stage_context_injection(ctx, 2),
            failure_modes_text=format_failure_modes_for_prompt(ctx),
        )

    def parse_output(self, raw_text: str, ctx: ProjectContext) -> ProjectContext:
        if settings.stage_output_mode == "json_first":
            result = self.parse_structured_output(raw_text, ctx)
            if result.parsed:
                schema = Stage2Schema.model_validate(result.parsed)
                ctx.stage_2_output = stage2_schema_to_output(schema, raw_text)
                ctx.parser_errors.pop("stage_2", None)
                return ctx
            ctx.parser_errors["stage_2"] = (
                "Structured output parse failed, fallback to Markdown parser: "
                + "; ".join(result.validation_errors)
            )

        if ctx.stage_2_output is None:
            ctx.stage_2_output = Stage2Output()

        ctx.stage_2_output.raw_summary = raw_text
        workflow_nodes = []

        table_pattern = re.compile(
            r"\|\s*([A-Za-z0-9_-]+)\s*\|"  # 节点ID
            r"\s*([^|\n]+)\s*\|"  # 阶段名称
            r"\s*([^|\n]+)\s*\|"  # 分配模型
            r"\s*([^|\n]+)\s*\|"  # 人工动作
            r"\s*([^|\n]+)\s*\|"  # 检查标准
            r"\s*([^|\n]+)\s*\|",  # 覆盖失败模式
            re.IGNORECASE,
        )

        prompt_blocks = re.findall(r"```prompt\s*([\s\S]+?)```", raw_text)

        node_index = 0
        for match in table_pattern.finditer(raw_text):
            node_id, stage_name, model, human_action, check_criteria, fm_ids = match.groups()
            if node_id.lower() in ("节点id", "id") or not node_id.strip("-"):
                continue

            fm_id_list = [x.strip() for x in re.split(r"[,，、]", fm_ids) if x.strip()]
            prompt_template = ""
            if node_index < len(prompt_blocks):
                prompt_template = prompt_blocks[node_index].strip()
                node_index += 1

            node = WorkflowNode(
                node_id=node_id.strip(),
                stage_name=stage_name.strip(),
                model_assigned=model.strip(),
                human_action=human_action.strip(),
                check_criteria=check_criteria.strip(),
                failure_modes_addressed=fm_id_list,
                prompt_template=prompt_template,
            )
            node.oversight_policy = infer_oversight_policy(node)
            workflow_nodes.append(node)

        if workflow_nodes:
            ctx.stage_2_output.workflow_nodes = workflow_nodes
            ctx.stage_2_output.total_stages = len(workflow_nodes)
            ctx.parser_errors.pop("stage_2", None)
        elif settings.stage_output_mode == "json_first":
            ctx.parser_errors["stage_2"] = "JSON 与 Markdown 解析均未得到 workflow_nodes。"

        return ctx
