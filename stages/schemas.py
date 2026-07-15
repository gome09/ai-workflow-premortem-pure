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
    affected_stakeholders: list[str] = Field(default_factory=list)
    possible_consequences: str = ""
    likelihood: Literal["low", "medium", "high"] = "medium"
    recommended_controls: str = ""
    open_questions: list[str] = Field(default_factory=list)


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
    ai_can_do: str = ""
    ai_cannot_do: str = ""
    trigger_conditions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)
    rollback_action: str = ""


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
    case_id: str = ""
    failure_mode_id: str = ""
    forbidden_behaviors: list[str] = Field(default_factory=list)
    evidence_type: Literal["demo_evidence", "production_evidence", "manual_evidence", "none"] = (
        "demo_evidence"
    )
    is_mock_evidence: bool = True
    human_review_result: Literal["pending", "approved", "rejected", "not_required"] = "pending"
    final_pass_status: Literal["passed", "failed", "pending", "blocked"] = "pending"  # noqa: S105


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


class DeploymentDecisionSchema(BaseModel):
    decision: Literal["go", "conditional_go", "pilot_only", "no_go"]
    decision_scope: Literal[
        "internal_testing_only",
        "limited_pilot",
        "conditional_deployment",
        "deployment_paused",
    ]
    decision_rationale: str = ""
    unresolved_risk_ids: list[str] = Field(default_factory=list)
    required_conditions: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    monitoring_requirements: list[str] = Field(default_factory=list)
    rollback_conditions: list[str] = Field(default_factory=list)
    prohibited_uses: list[str] = Field(default_factory=list)
    review_after: str = ""
    human_accountable_role: str = ""
    is_demo_recommendation: bool = True


class Stage4Schema(BaseModel):
    trigger_methods: list[TriggerMethodSchema]
    final_notes: str = ""
    deployment_decision: DeploymentDecisionSchema | None = None


# TODO: 各 Stage 的 Schema 和 core/models.py 里的 StageXOutput 有重复
# 应该统一成一套，或者让 schemas.py 只做 LLM 输出解析，models.py 做业务存储
