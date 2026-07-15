# stages/stage_3_stress_test.py
from __future__ import annotations

import re

from core.config import settings
from core.context_manager import build_stage_context_injection
from core.eval_service import sync_eval_cases_from_stage3
from core.models import ProjectContext, Stage3Output, StressTestResult, WorkflowNode
from core.scenario_context import current_domain_profile
from core.stage3_result_calculator import apply_deterministic_overall_passed
from stages.base import BaseStageExecutor
from stages.json_prompts import JSON_OUTPUT_RULES, get_json_prompts
from stages.prompts import get_stage_prompts
from stages.schemas import Stage3Schema
from stages.validators import stage3_schema_to_output
from tools.safety_classifier import add_findings_dedup, scan_stage3_test_cases


def _infer_scenario_type(text: str) -> str:
    lowered = (text or "").lower()
    if any(token in lowered for token in ["adversarial", "攻击", "对抗", "注入", "越狱"]):
        return "adversarial"
    if any(token in lowered for token in ["edge", "边界", "异常", "极端"]):
        return "edge"
    return "normal"


class Stage3Executor(BaseStageExecutor):
    stage_id = 3

    def _select_target_nodes(self, ctx: ProjectContext, max_nodes: int = 5) -> list[WorkflowNode]:
        """Select stress-test nodes with high-risk coverage first.

        Stage 3 used to target a single node. v0.5 keeps the deterministic runner
        but asks the LLM to produce cases across the most risk-bearing nodes.
        """
        if not ctx.stage_2_output or not ctx.stage_2_output.workflow_nodes:
            return []

        severity_weight = {"critical": 4, "high": 3, "medium": 1, "low": 0}
        fm_weights = {
            fm.id: severity_weight.get(str(fm.severity).lower(), 0)
            for fm in (ctx.stage_1_output.failure_modes if ctx.stage_1_output else [])
        }

        scored: list[tuple[int, int, WorkflowNode]] = []
        for index, node in enumerate(ctx.stage_2_output.workflow_nodes):
            addressed = node.failure_modes_addressed or []
            score = sum(fm_weights.get(fm_id, 0) for fm_id in addressed)
            high_risk_hits = sum(1 for fm_id in addressed if fm_weights.get(fm_id, 0) >= 3)
            scored.append((score, high_risk_hits, node))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = [node for score, hits, node in scored if score > 0 or hits > 0]
        if not selected:
            selected = [node for _, _, node in scored]
        return selected[:max_nodes]

    def _select_target_node(self, ctx: ProjectContext) -> WorkflowNode | None:
        """Backward-compatible helper for Markdown fallback parsing."""
        nodes = self._select_target_nodes(ctx, max_nodes=1)
        return nodes[0] if nodes else None

    def _format_target_nodes(self, nodes: list[WorkflowNode]) -> str:
        if not nodes:
            return "(workflow node data is missing; use the stage 2 workflow design if available)"
        blocks = []
        for node in nodes:
            blocks.append(
                "\n".join(
                    [
                        f"Node ID: {node.node_id}",
                        f"Stage Name: {node.stage_name}",
                        f"Model Assigned: {node.model_assigned}",
                        f"Human Action: {node.human_action}",
                        f"Check Criteria: {node.check_criteria}",
                        f"Failure Modes Addressed: {', '.join(node.failure_modes_addressed or []) or 'none'}",
                        "Prompt Template:",
                        node.prompt_template,
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks)

    def build_system_prompt(self, ctx: ProjectContext) -> str:
        target_nodes = self._select_target_nodes(ctx)
        target_nodes_text = self._format_target_nodes(target_nodes)

        profile = current_domain_profile(ctx)
        _prompts = get_stage_prompts(profile)
        _json = get_json_prompts(profile)
        template = (
            _json["stage_3"] if settings.stage_output_mode == "json_first" else _prompts["stage_3"]
        )
        return template.format(
            JSON_OUTPUT_RULES=JSON_OUTPUT_RULES,
            context_summary=build_stage_context_injection(ctx, 3),
            target_nodes_text=target_nodes_text,
        )

    def parse_output(self, raw_text: str, ctx: ProjectContext) -> ProjectContext:
        if settings.stage_output_mode == "json_first":
            result = self.parse_structured_output(raw_text, ctx)
            if result.parsed:
                schema = Stage3Schema.model_validate(result.parsed)
                ctx.stage_3_output = stage3_schema_to_output(schema, raw_text)
                add_findings_dedup(ctx, scan_stage3_test_cases(ctx))
                sync_eval_cases_from_stage3(ctx)
                ctx.parser_errors.pop("stage_3", None)
                # 确定性计算 overall_passed
                if ctx.stage_3_output and ctx.stage_3_output.test_results:
                    apply_deterministic_overall_passed(ctx)
                return ctx
            ctx.parser_errors["stage_3"] = (
                "Structured output parse failed, fallback to Markdown parser: "
                + "; ".join(result.validation_errors)
            )

        if ctx.stage_3_output is None:
            ctx.stage_3_output = Stage3Output()

        ctx.stage_3_output.raw_summary = raw_text
        passed_keywords = ["整体通过", "overall passed", "压测通过"]
        failed_keywords = ["整体未通过", "overall failed", "压测未通过", "不通过"]

        if any(kw in raw_text for kw in passed_keywords):
            ctx.stage_3_output.overall_passed = True
        elif any(kw in raw_text for kw in failed_keywords):
            ctx.stage_3_output.overall_passed = False

        scene_pattern = re.compile(
            r"### 场景\[?(\d+)\]?[：:]\s*(.+?)\n"
            r"[\s\S]+?测试输入[：:]\s*(.+?)\n"
            r"[\s\S]+?预期\s*AI\s*输出[：:]\s*(.+?)\n"
            r"[\s\S]+?预测错误[：:]\s*(.+?)\n",
            re.IGNORECASE,
        )

        results = []
        target_node = self._select_target_node(ctx)
        node_id = target_node.node_id if target_node else "unknown"

        for match in scene_pattern.finditer(raw_text):
            _, scene_type, test_input, ai_output, error_pred = match.groups()
            results.append(
                StressTestResult(
                    tested_node_id=node_id,
                    scenario_type=_infer_scenario_type(scene_type),
                    test_input=test_input.strip(),
                    ai_output=ai_output.strip(),
                    error_predictions=[error_pred.strip()],
                    passed=ctx.stage_3_output.overall_passed,
                    raw_summary=match.group(0),
                )
            )

        if results:
            ctx.stage_3_output.test_results = results
            add_findings_dedup(ctx, scan_stage3_test_cases(ctx))
            sync_eval_cases_from_stage3(ctx)
            ctx.parser_errors.pop("stage_3", None)
        elif settings.stage_output_mode == "json_first":
            ctx.parser_errors["stage_3"] = "JSON 与 Markdown 解析均未得到 test_results。"

        # 确定性计算 overall_passed，不信任 fixture 硬编码值
        if ctx.stage_3_output and ctx.stage_3_output.test_results:
            apply_deterministic_overall_passed(ctx)

        return ctx
