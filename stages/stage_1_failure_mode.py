# stages/stage_1_failure_mode.py
from __future__ import annotations

import re

from core.config import settings
from core.context_manager import build_stage_context_injection
from core.evidence_service import (
    evidence_sources_from_search_results,
    evidence_sources_from_user_materials,
    extract_evidence_ids,
    format_evidence_for_prompt,
    link_failure_modes_to_evidence,
)
from core.models import FailureMode, ProjectContext, Stage1Output
from stages.base import BaseStageExecutor
from stages.json_prompts import JSON_OUTPUT_RULES, STAGE_1_JSON_SYSTEM
from stages.prompts import STAGE_1_SYSTEM
from stages.schemas import Stage1Schema
from stages.validators import stage1_schema_to_output
from tools.safety_classifier import add_findings_dedup, scan_evidence_sources
from tools.search import research_tool


class Stage1Executor(BaseStageExecutor):
    stage_id = 1

    def _prepare_materials(self, ctx: ProjectContext) -> str:
        # 第一次进入时执行搜索，后续对话复用缓存的资料
        if not ctx.stage_1_output or not ctx.stage_1_output.search_sources:
            search_results = research_tool.search(ctx)
            evidence_sources = evidence_sources_from_search_results(ctx, search_results)
            user_evidence_sources = evidence_sources_from_user_materials(
                ctx,
                ctx.user_materials,
                start_index=0,
            )
            # Note: deduplication is handled by add_or_update_evidence() inside
            # evidence_sources_from_search_results / evidence_sources_from_user_materials.
            # Using dict.fromkeys() here would fail because EvidenceSource is unhashable.
            all_evidence_sources = evidence_sources + user_evidence_sources
            add_findings_dedup(ctx, scan_evidence_sources(ctx, all_evidence_sources, stage_id=1))
            materials_text = format_evidence_for_prompt(ctx.evidence_sources, ctx.user_materials)
            if ctx.stage_1_output is None:
                ctx.stage_1_output = Stage1Output()
            ctx.stage_1_output.search_sources = [r.url for r in search_results]
        else:
            materials_text = format_evidence_for_prompt(ctx.evidence_sources, ctx.user_materials)
        return materials_text

    def build_system_prompt(self, ctx: ProjectContext) -> str:
        materials_text = self._prepare_materials(ctx)
        template = (
            STAGE_1_JSON_SYSTEM if settings.stage_output_mode == "json_first" else STAGE_1_SYSTEM
        )
        return template.format(
            JSON_OUTPUT_RULES=JSON_OUTPUT_RULES,
            context_summary=build_stage_context_injection(ctx, 1),
            research_target=ctx.research_target,
            domain=ctx.domain,
            goal=ctx.goal,
            materials=materials_text,
        )

    def parse_output(self, raw_text: str, ctx: ProjectContext) -> ProjectContext:
        """JSON-first 解析，失败后回落到旧 Markdown 表格解析。"""
        search_sources = ctx.stage_1_output.search_sources if ctx.stage_1_output else []
        if settings.stage_output_mode == "json_first":
            result = self.parse_structured_output(raw_text, ctx)
            if result.parsed:
                schema = Stage1Schema.model_validate(result.parsed)
                ctx.stage_1_output = stage1_schema_to_output(
                    schema, raw_text, search_sources=search_sources
                )
                link_failure_modes_to_evidence(ctx)
                ctx.parser_errors.pop("stage_1", None)
                return ctx
            ctx.parser_errors["stage_1"] = (
                "Structured output parse failed, fallback to Markdown parser: "
                + "; ".join(result.validation_errors)
            )

        if ctx.stage_1_output is None:
            ctx.stage_1_output = Stage1Output(search_sources=search_sources)
        ctx.stage_1_output.raw_summary = raw_text
        ctx.stage_1_output.search_sources = search_sources
        failure_modes = []

        table_pattern = re.compile(
            r"\|\s*([A-Za-z0-9_-]+)\s*\|"  # ID
            r"\s*([^|\n]+)\s*\|"  # 类别
            r"\s*([^|\n]+)\s*\|"  # 描述
            r"\s*(critical|high|medium|low)\s*\|"  # 严重程度
            r"\s*([^|\n]+)\s*\|",  # 依据
            re.IGNORECASE,
        )

        for match in table_pattern.finditer(raw_text):
            fm_id, category, description, severity, evidence = match.groups()
            if fm_id.lower() in ("节点id", "失败模式id", "id") or not fm_id.strip("-"):
                continue
            failure_modes.append(
                FailureMode(
                    id=fm_id.strip(),
                    category=category.strip(),
                    description=description.strip(),
                    severity=severity.strip().lower(),
                    evidence=evidence.strip(),
                    evidence_ids=extract_evidence_ids(evidence.strip()),
                    needs_verification="需核验" in description or "需核验" in evidence,
                )
            )

        if failure_modes:
            ctx.stage_1_output.failure_modes = failure_modes
            link_failure_modes_to_evidence(ctx)
            ctx.parser_errors.pop("stage_1", None)
        elif settings.stage_output_mode == "json_first":
            ctx.parser_errors["stage_1"] = "JSON 与 Markdown 解析均未得到 failure_modes。"

        conclusion_match = re.search(r"直接结论[：:]\s*\n?([\s\S]+?)(?:\n#|\n##|\Z)", raw_text)
        if conclusion_match:
            ctx.stage_1_output.direct_conclusion = conclusion_match.group(1).strip()

        return ctx
