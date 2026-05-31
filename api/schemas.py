# api/schemas.py
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class SessionListItem(BaseModel):
    session_id: str
    current_state: str
    research_target: str
    domain: str
    updated_at: str


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


class RunEvalCasesRequest(BaseModel):
    eval_ids: list[str] | None = None
    run_mode: Literal["manual", "dry_run", "llm_node"] = "manual"


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
    run_mode: Literal["manual", "dry_run", "llm_node"] = "manual"
    provider: str | None = None
    model: str | None = None
    baseline_experiment_id: str | None = None
    run_config: dict[str, Any] = Field(default_factory=dict)


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
    reviewer_id: str = "human_reviewer"
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
