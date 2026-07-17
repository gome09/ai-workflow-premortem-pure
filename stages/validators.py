# stages/validators.py
from __future__ import annotations

import json
import re
from typing import Any, Literal, cast

from pydantic import ValidationError

from core.models import (
    FailureMode,
    HumanOversightPolicy,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
    StressTestResult,
    TriggerMethod,
    WorkflowNode,
)
from stages.schemas import Stage1Schema, Stage2Schema, Stage3Schema, Stage4Schema


class StageValidationError(ValueError):
    """阶段 JSON 输出无法通过 schema 校验。"""


def extract_json_object(raw_text: str) -> dict[str, Any] | None:
    """从完整回复或 markdown code block 中提取 JSON object。"""
    text = (raw_text or "").strip()
    if not text:
        return None

    candidates: list[str] = []
    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]+?)```", text, flags=re.IGNORECASE)
    candidates.extend(block.strip() for block in fenced_blocks)
    candidates.append(text)

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                loaded = json.loads(candidate[start : end + 1])
                if isinstance(loaded, dict):
                    return loaded
            except json.JSONDecodeError:
                continue
    return None


def validate_stage1(raw_text: str) -> Stage1Schema:
    payload = extract_json_object(raw_text)
    if payload is None:
        raise StageValidationError("未找到可解析的 JSON 对象")
    try:
        return Stage1Schema.model_validate(payload)
    except ValidationError as exc:
        raise StageValidationError(str(exc)) from exc


def validate_stage2(raw_text: str) -> Stage2Schema:
    payload = extract_json_object(raw_text)
    if payload is None:
        raise StageValidationError("未找到可解析的 JSON 对象")
    try:
        return Stage2Schema.model_validate(payload)
    except ValidationError as exc:
        raise StageValidationError(str(exc)) from exc


def validate_stage3(raw_text: str) -> Stage3Schema:
    payload = extract_json_object(raw_text)
    if payload is None:
        raise StageValidationError("未找到可解析的 JSON 对象")
    try:
        return Stage3Schema.model_validate(payload)
    except ValidationError as exc:
        raise StageValidationError(str(exc)) from exc


def validate_stage4(raw_text: str) -> Stage4Schema:
    payload = extract_json_object(raw_text)
    if payload is None:
        raise StageValidationError("未找到可解析的 JSON 对象")
    try:
        return Stage4Schema.model_validate(payload)
    except ValidationError as exc:
        raise StageValidationError(str(exc)) from exc


def stage1_schema_to_output(
    schema: Stage1Schema, raw_text: str, search_sources: list[str] | None = None
) -> Stage1Output:
    return Stage1Output(
        failure_modes=[
            FailureMode(
                id=item.id,
                category=item.category,
                description=item.description,
                severity=item.severity,
                evidence=item.evidence,
                evidence_ids=list(dict.fromkeys(item.evidence_ids)),
                needs_verification=(
                    item.requires_human_review
                    or "需核验" in item.description
                    or "需核验" in item.evidence
                ),
            )
            for item in schema.failure_modes
        ],
        direct_conclusion=schema.direct_conclusion,
        search_sources=search_sources or [],
        raw_summary=raw_text,
    )


def _infer_policy_from_schema(node) -> HumanOversightPolicy | None:
    # Always infer a policy for every workflow node — even low-risk nodes
    # benefit from a lightweight oversight record.  The gate rule only blocks
    # when a high/critical failure-mode is addressed *and* policy is None, so
    # returning a policy here never relaxes a real safety gate.
    required_action = "verify_evidence" if node.evidence_required else "approve"
    risk_level = node.oversight_risk_level if hasattr(node, "oversight_risk_level") else "medium"
    return HumanOversightPolicy(
        stage_id=2,
        risk_level=cast(Literal["low", "medium", "high", "critical"], risk_level),
        trigger_reason=f"节点 {node.node_id} 的工作流步骤需要监督确认",
        required_action=cast(
            Literal["approve", "edit", "reject", "verify_evidence", "escalate"], required_action
        ),
        can_auto_continue=getattr(node, "can_auto_continue", False),
        evidence_required=getattr(node, "evidence_required", False),
    )


def stage2_schema_to_output(schema: Stage2Schema, raw_text: str) -> Stage2Output:
    nodes = []
    for item in schema.workflow_nodes:
        nodes.append(
            WorkflowNode(
                node_id=item.node_id,
                stage_name=item.stage_name,
                model_assigned=item.model_assigned,
                human_action=item.human_action,
                check_criteria="；".join(item.check_criteria),
                failure_modes_addressed=item.addressed_failure_mode_ids,
                prompt_template=item.prompt_template,
                oversight_policy=_infer_policy_from_schema(item),
            )
        )
    return Stage2Output(workflow_nodes=nodes, total_stages=len(nodes), raw_summary=raw_text)


def stage3_schema_to_output(schema: Stage3Schema, raw_text: str) -> Stage3Output:
    results = []
    for item in schema.test_cases:
        predictions = [item.predicted_failure] if item.predicted_failure else []
        corrections = [item.correction_prompt] if item.correction_prompt else []
        results.append(
            StressTestResult(
                tested_node_id=item.target_node_id,
                scenario_type=item.scenario_type,
                test_input=item.test_input,
                ai_output=item.expected_behavior,
                error_predictions=predictions,
                correction_prompts=corrections,
                pass_criteria=list(item.pass_criteria or []),
                passed=item.passed,
                raw_summary=raw_text,
            )
        )
    return Stage3Output(
        test_results=results, overall_passed=schema.overall_passed, raw_summary=raw_text
    )


def stage4_schema_to_output(schema: Stage4Schema, raw_text: str) -> Stage4Output:
    return Stage4Output(
        trigger_methods=[
            TriggerMethod(
                node_id=item.node_id,
                model_or_mode=item.model_or_mode,
                entry_point=item.entry_point,
                trigger_instruction=item.trigger_instruction,
                execution_suggestion=item.execution_suggestion,
                human_review_required=item.human_review_required,
            )
            for item in schema.trigger_methods
        ],
        raw_summary=raw_text,
    )
