# stages/schemas.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FailureModeSchema(BaseModel):
    id: str
    category: str
    description: str
    severity: Literal["low", "medium", "high", "critical"]
    evidence_ids: list[str] = Field(default_factory=list)
    evidence: str = ""
    mitigation_hint: str | None = None
    requires_human_review: bool = False


class Stage1Schema(BaseModel):
    failure_modes: list[FailureModeSchema]
    direct_conclusion: str
    open_questions: list[str] = Field(default_factory=list)


class WorkflowNodeSchema(BaseModel):
    node_id: str
    stage_name: str
    model_assigned: str
    human_action: str
    check_criteria: list[str] = Field(default_factory=list)
    addressed_failure_mode_ids: list[str] = Field(default_factory=list)
    prompt_template: str = ""
    human_review_required: bool = False
    oversight_risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    evidence_required: bool = False
    can_auto_continue: bool = True


class Stage2Schema(BaseModel):
    workflow_nodes: list[WorkflowNodeSchema]
    design_rationale: str = ""
    open_questions: list[str] = Field(default_factory=list)


class StressTestCaseSchema(BaseModel):
    case_id: str
    target_node_id: str
    scenario_type: Literal["normal", "edge", "adversarial"]
    test_input: str
    expected_behavior: str
    predicted_failure: str | None = None
    correction_prompt: str | None = None
    pass_criteria: list[str] = Field(default_factory=list)
    passed: bool = False


class Stage3Schema(BaseModel):
    test_cases: list[StressTestCaseSchema]
    overall_passed: bool
    risk_summary: str = ""


class TriggerMethodSchema(BaseModel):
    node_id: str
    model_or_mode: str = ""
    entry_point: str
    trigger_instruction: str
    execution_suggestion: str
    human_review_required: bool = False


class Stage4Schema(BaseModel):
    trigger_methods: list[TriggerMethodSchema]
    final_notes: str = ""


# TODO: 各 Stage 的 Schema 和 core/models.py 里的 StageXOutput 有重复
# 应该统一成一套，或者让 schemas.py 只做 LLM 输出解析，models.py 做业务存储
