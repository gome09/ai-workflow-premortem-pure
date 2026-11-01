# api/schemas.py
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.stage_resolution_service import StageResolutionOperation


class SendMessageRequest(BaseModel):
    user_input: str
    user_materials: list[str] | None = None


class SendMessageResponse(BaseModel):
    session_id: str
    ai_reply: str
    current_state: str
    pending_flags_count: int
    pending_actions_count: int = 0
    stage_advancement_decision: dict[str, Any] | None = None
    next_required_operation: dict[str, Any] | None = None
    stage_resolution_summary: dict[str, Any] | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    current_state: str
    selected_scenario_id: str | None = None


class CreateSessionRequest(BaseModel):
    scenario_id: str | None = None


class RenameSessionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ScenarioSummaryResponse(BaseModel):
    scenario_id: str
    name: str
    description: str
    input_sample_path: str
    domain_profile: str
    mock_fixture: str
    default_config: dict[str, Any] = Field(default_factory=dict)
    applicable_stages: list[str] = Field(default_factory=list)
    input_sample: str | None = None


class SessionListItem(BaseModel):
    session_id: str
    current_state: str
    session_name: str = ""
    scenario_name: str = ""
    research_target: str
    domain: str
    updated_at: str


class SessionOverviewResponse(BaseModel):
    """会话首屏轻量概览；不包含 stage 输出、轨迹与评测明细。"""

    session_id: str
    session_name: str = ""
    current_state: str
    selected_scenario_id: str | None = None
    data_classification: str
    created_at: datetime
    updated_at: datetime
    conversation_history: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    flagged_items: list[dict[str, Any]] = Field(default_factory=list)
    pending_actions: list[dict[str, Any]] = Field(default_factory=list)


class ResolveFlagRequest(BaseModel):
    flag_id: str
    action: str  # 'verified' | 'dismissed'
    note: str = ""


class AddMaterialsRequest(BaseModel):
    materials: list[str]


class ResolveActionRequest(BaseModel):
    decision: Literal[
        "approve",
        "edit",
        "reject",
        "verify_evidence",
        "escalate",
        "verified",
        "dismissed",
    ]
    note: str = ""
    payload_after: dict | None = None
    idempotency_key: str | None = None
    expected_before_hash: str | None = None


class VerifyEvidenceRequest(BaseModel):
    note: str = ""


class ResolveSafetyFindingRequest(BaseModel):
    status: Literal["resolved", "dismissed"]
    note: str = ""


class ScoreEvalCaseRequest(BaseModel):
    human_score: int | None = None
    human_comment: str = ""
    passed: bool | None = None
    actual_output: str | None = None


class TargetSystemConfigRequest(BaseModel):
    """Real target system HTTP JSON contract."""

    endpoint: str
    timeout_seconds: float = Field(default=10.0, gt=0)
    output_field: str = "output"


class RunEvalCasesRequest(BaseModel):
    eval_ids: list[str] | None = None
    run_mode: Literal["manual", "dry_run", "llm_node", "target_http"] = "manual"
    target_config: TargetSystemConfigRequest | None = None


class StageRerunRequest(BaseModel):
    reason: str = ""
    note: str = ""


class StageRevisionRequest(BaseModel):
    reason: str = ""
    note: str = ""


class StageRollbackRequest(BaseModel):
    to_stage: int
    reason: str = ""
    note: str = ""
    target_running: bool = False


class StageActionSyncRequest(BaseModel):
    reason: str = "manual_sync_review_actions"


class StageAdvanceRequest(BaseModel):
    reason: str = "api_stage_advance"


class ActionResolutionResponse(BaseModel):
    session_id: str
    action_id: str
    requested_status: str
    result_status: str
    action_status: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    log_id: str | None = None
    error_message: str | None = None
    current_state: str | None = None
    stage_id: int | None = None
    stage_advancement_decision: dict[str, Any] | None = None
    next_required_operation: dict[str, Any] | None = None
    runtime_validation: str = "deferred_by_instruction"


class CreateEvalDatasetRequest(BaseModel):
    name: str
    description: str = ""
    case_ids: list[str] = Field(default_factory=list)
    scenario_type: str = "mixed"
    source: str = "manual"
    version: str = "0.1"
    tags: list[str] = Field(default_factory=list)


class CreateEvalDatasetFromStage3Request(BaseModel):
    name: str = "Stage 3 generated dataset"
    description: str = ""
    version: str = "0.1"
    owner: str = "system"


class UpdateEvalDatasetCasesRequest(BaseModel):
    eval_ids: list[str]


class SetEvalDatasetBaselineRequest(BaseModel):
    baseline_experiment_id: str | None = None


class CreateEvalExperimentRequest(BaseModel):
    dataset_id: str
    name: str
    description: str = ""
    run_mode: Literal["manual", "dry_run", "llm_node", "target_http"] = "manual"
    provider: str | None = None
    model: str | None = None
    baseline_experiment_id: str | None = None
    run_config: dict[str, Any] = Field(default_factory=dict)
    target_config: TargetSystemConfigRequest | None = None


class RunEvalExperimentRequest(BaseModel):
    dry_run_only: bool = True


class CompareEvalExperimentRequest(BaseModel):
    baseline_experiment_id: str | None = None


class GenerateRedTeamCasesRequest(BaseModel):
    stage: int = 3


class CreateRedTeamCaseRequest(BaseModel):
    attack_type: str = "unsupported_claim"
    prompt: str
    expected_failure_mode: str
    expected_safe_behavior: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    target_stage: int = 3
    target_node_id: str | None = None
    source_finding_id: str | None = None
    source_failure_mode_id: str | None = None
    malicious_material: str = ""
    taxonomy_refs: list[str] = Field(default_factory=list)
    control_refs: list[str] = Field(default_factory=list)


class ResolveRedTeamCaseRequest(BaseModel):
    note: str = ""


class CreateRedTeamDatasetRequest(BaseModel):
    name: str = "Red Team generated dataset"
    description: str = "Approved RedTeamCase records synced into EvalCase for regression gate use."
    case_ids: list[str] | None = None
    version: str = "0.1"
    owner: str = "system"


class CalibrateEvalRunRequest(BaseModel):
    human_label: Literal["passed", "failed", "needs_review"]
    human_comment: str = ""
    disagreement_reason: str = ""


class TraceToEvalCaseRequest(BaseModel):
    expected_behavior: str | None = None
    target_node_id: str | None = None


class TraceToEvalDatasetRequest(BaseModel):
    trace_ids: list[str] | None = None
    name: str = "Trace backfill regression dataset"
    description: str = "EvalCases generated from failed/parser/safety traces for regression gating."
    version: str = "0.1"
    owner: str = "system"


class UpdateDataClassificationRequest(BaseModel):
    data_classification: Literal["public_demo", "business_internal", "sensitive_personal"]
    note: str = ""


class TargetDeploymentRequest(BaseModel):
    endpoint: str
    version: str


class UpdateEvalCaseRequest(BaseModel):
    target_node_id: str | None = None
    input_payload: str | None = None
    expected_behavior: str | None = None
    pass_criteria: list[str] | None = None
    scenario_type: (
        Literal[
            "normal",
            "edge",
            "adversarial",
            "regression",
            "production_failure",
            "safety",
            "evidence",
            "parser",
        ]
        | None
    ) = None
    covered_failure_mode_ids: list[str] | None = None


class RenameSessionResponse(BaseModel):
    session_id: str
    session_name: str


class UpdateDataClassificationResponse(BaseModel):
    ok: bool = True
    session_id: str
    before: str
    after: str
    is_downgrade: bool


class RecoverWorkflowRequest(BaseModel):
    target_state: str
    note: str = ""


class RecoverWorkflowResponse(BaseModel):
    ok: bool = True
    session_id: str
    before: str
    after: str
    last_error: str = ""


class DeleteSessionResponse(BaseModel):
    """删除会话的收尾摘要。归档行数等附加字段允许透传。"""

    model_config = ConfigDict(extra="allow")

    session_id: str
    tenant_id: str = ""
    session_name: str = ""
    research_target: str = ""
    domain: str = ""
    current_state: str
    data_classification: str = ""
    created_at: str = ""
    updated_at: str = ""
    purged_by: str = ""
    archived_audit_events: int | None = None


class StageOperationResultResponse(BaseModel):
    """阶段变更操作的通用信封。

    `result` 随操作类型变化，因此保留扩展字段透传，避免响应被静默裁剪。
    """

    model_config = ConfigDict(extra="allow")

    session_id: str
    operation: str
    result: Any = None
    result_type: str = ""
    stage_id: int
    stage_advancement_decision: dict[str, Any] | None = None
    next_required_operation: dict[str, Any] | None = None
    runtime_validation: str = "deferred_by_instruction"


class MaterialsAddedResponse(StageOperationResultResponse):
    ok: bool = True
    materials_added_count: int = 0
    user_materials_count: int = 0
    evidence_sources_count: int = 0
    safety_findings_count: int = 0


class ResolveFlagResponse(StageOperationResultResponse):
    ok: bool = True
    flag_id: str
    action: str
    note: str = ""
    resolved_action_ids: list[str] = Field(default_factory=list)
    resolved_actions_count: int = 0


class ExportReportResponse(BaseModel):
    """导出结果：markdown 为 {format, content}，json 直接返回报告字典。"""

    model_config = ConfigDict(extra="allow")

    format: str | None = None
    content: Any = None


class StageResolutionSummaryResponse(BaseModel):
    """四阶段阻断项与可执行操作的汇总视图。"""

    model_config = ConfigDict(extra="allow")

    by_stage: dict[str, list[StageResolutionOperation]] = Field(default_factory=dict)
    current_stage_id: int | None = None
    actionable_stage_ids: list[int] = Field(default_factory=list)
    future_stage_placeholders: list[dict[str, Any]] = Field(default_factory=list)
    total_operations: int = 0
    hard_blockers_count: int = 0
    overridable_blockers_count: int = 0
    executable_operations_count: int = 0
    hard_blockers: list[StageResolutionOperation] = Field(default_factory=list)
    overridable_blockers: list[StageResolutionOperation] = Field(default_factory=list)
    current_required_operations: list[StageResolutionOperation] = Field(default_factory=list)


class StageResolutionOperationsResponse(BaseModel):
    stage_id: int
    operations: list[StageResolutionOperation] = Field(default_factory=list)


class RiskTreatmentUpsertRequest(BaseModel):
    source_type: Literal["failure_mode", "safety_finding"]
    source_id: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    mitigation_plan: str = Field(min_length=1)
    status: Literal["planned", "in_progress", "completed", "accepted"] = "planned"
    note: str = ""


class RiskTreatmentReviewRequest(BaseModel):
    decision: Literal["accept", "reject"]
    note: str = ""


class ReleaseApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = ""


class RiskFactorScoresRequest(BaseModel):
    impact: int = Field(ge=0, le=3)
    autonomy: int = Field(ge=0, le=3)
    data_sensitivity: int = Field(ge=0, le=3)
    reversibility: int = Field(ge=0, le=3)
    scale: int = Field(ge=0, le=3)
    external_exposure: int = Field(ge=0, le=3)
    rationale: str = ""


class RiskOverrideRequest(BaseModel):
    requested_tier: Literal["low", "medium", "high", "critical"]
    reason: str = Field(min_length=1, max_length=500)


class RiskProfileResponse(BaseModel):
    session_id: str
    factors: dict[str, int]
    structural_tier: str
    floor_tier: str
    effective_tier: str
    reasons: list[str] = Field(default_factory=list)
    source: str
    llm_explanation: str = ""
    override: dict[str, Any] | None = None
    overrides: list[dict[str, Any]] = Field(default_factory=list)
