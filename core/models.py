# core/models.py
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# FIXME: ProjectContext 这个模型字段太多了（890行），应该拆成子模型
# 但因为 LangGraph state 需要是单一 dict，拆分会影响 graph 的状态传递
# 先这样，后面有时间再重构

# ─────────────────────────────────────────────
# 枚举定义
# ─────────────────────────────────────────────


class SessionState(StrEnum):
    """会话状态机的所有合法状态"""

    INIT = "init"
    S1_RUNNING = "s1_running"
    S1_REVIEW = "s1_review"
    S2_RUNNING = "s2_running"
    S2_REVIEW = "s2_review"
    S3_RUNNING = "s3_running"
    S3_REVIEW = "s3_review"
    S4_RUNNING = "s4_running"
    S4_REVIEW = "s4_review"
    ITERATING = "iterating"
    COMPLETE = "complete"


class ReviewAction(StrEnum):
    """人工审核动作"""

    APPROVE = "approve"  # 确认，进入下一阶段
    REVISE = "revise"  # 修改当前阶段
    BACK = "back"  # 回退上一阶段
    BACK_TO_DESIGN = "back_to_design"  # 阶段三专用：回退到阶段二


class FlagStatus(StrEnum):
    """【需核验】项状态"""

    PENDING = "pending"
    VERIFIED = "verified"
    DISMISSED = "dismissed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class HumanActionType(StrEnum):
    """正式人工监督动作类型。"""

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    VERIFY_EVIDENCE = "verify_evidence"
    ESCALATE = "escalate"


class HumanActionStatus(StrEnum):
    """人工监督动作状态。"""

    PENDING = "pending"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    STALE = "stale"


class AuditActor(StrEnum):
    """审计事件的发起方。"""

    SYSTEM = "system"
    USER = "user"
    AI = "ai"


CONTEXT_SCHEMA_VERSION = "0.9.0"
ACTION_SCHEMA_VERSION = "0.7.0"


# ─────────────────────────────────────────────
# 基础消息
# ─────────────────────────────────────────────


class Message(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# 各阶段结构化输出
# ─────────────────────────────────────────────


class FailureMode(BaseModel):
    """单条失败模式"""

    id: str
    category: str  # 失败类别（如：幻觉、推理断链、上下文遗忘等）
    description: str  # 具体描述
    severity: Literal["critical", "high", "medium", "low"]
    evidence: str = ""  # 来源/依据的可读文本
    evidence_ids: list[str] = Field(default_factory=list)  # 结构化 evidence_id 引用
    needs_verification: bool = False  # 是否标注了【需核验】


class Stage1Output(BaseModel):
    """阶段一输出：失败模式识别"""

    failure_modes: list[FailureMode] = Field(default_factory=list)
    direct_conclusion: str = ""  # 直接结论摘要
    search_sources: list[str] = Field(default_factory=list)
    raw_summary: str = ""  # AI 的完整原始输出


class HumanOversightPolicy(BaseModel):
    """阶段输出对应的人工监督策略。"""

    policy_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    stage_id: int
    risk_level: Literal["low", "medium", "high", "critical"]
    trigger_reason: str
    required_action: Literal["approve", "edit", "reject", "verify_evidence", "escalate"]
    required_role: str | None = None
    can_auto_continue: bool = False
    evidence_required: bool = False


class WorkflowNode(BaseModel):
    """工作流中的单个节点"""

    node_id: str
    stage_name: str
    model_assigned: str  # 分配的模型/模式
    human_action: str  # 人工动作描述
    check_criteria: str  # 检查标准
    failure_modes_addressed: list[str]  # 对应的失败模式 ID
    prompt_template: str  # 该节点的 Prompt 模板
    oversight_policy: HumanOversightPolicy | None = None


class Stage2Output(BaseModel):
    """阶段二输出：工作流设计"""

    workflow_nodes: list[WorkflowNode] = Field(default_factory=list)
    total_stages: int = 0
    raw_summary: str = ""


class StressTestResult(BaseModel):
    """压测结果"""

    tested_node_id: str
    scenario_type: Literal["normal", "edge", "adversarial"] = "normal"
    test_input: str
    ai_output: str
    error_predictions: list[str] = Field(default_factory=list)
    correction_prompts: list[str] = Field(default_factory=list)
    pass_criteria: list[str] = Field(default_factory=list)
    passed: bool = False
    raw_summary: str = ""


class Stage3Output(BaseModel):
    """阶段三输出：压测"""

    test_results: list[StressTestResult] = Field(default_factory=list)
    overall_passed: bool = False
    raw_summary: str = ""


class TriggerMethod(BaseModel):
    """单个触发方式"""

    node_id: str
    model_or_mode: str
    entry_point: str  # 入口描述
    trigger_instruction: str  # 具体触发指令
    execution_suggestion: str  # 执行建议
    human_review_required: bool = False


class Stage4Output(BaseModel):
    """阶段四输出：触发方式"""

    trigger_methods: list[TriggerMethod] = Field(default_factory=list)
    raw_summary: str = ""


# ─────────────────────────────────────────────
# 【需核验】追踪
# ─────────────────────────────────────────────


class FlaggedItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    stage: int
    content: str  # 被标注的原文
    context: str = ""  # 上下文片段
    status: FlagStatus = FlagStatus.PENDING
    verified_by: str | None = None
    verified_at: datetime | None = None
    note: str = ""  # 处理备注


class MigrationRecord(BaseModel):
    """ProjectContext schema migration audit record."""

    from_version: str
    to_version: str
    migration_name: str
    migrated_at: datetime = Field(default_factory=datetime.utcnow)
    warnings: list[str] = Field(default_factory=list)


class PendingHumanAction(BaseModel):
    """需要人类处理的正式审核动作。"""

    action_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str
    stage_id: int
    node_id: str | None = None
    source_type: str = ""  # flag | failure_mode | parser | stress_test | evidence | safety_finding | trigger_method
    source_id: str | None = None
    action_type: Literal["approve", "edit", "reject", "verify_evidence", "escalate"]
    title: str
    description: str
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    trigger_reason: str = ""
    payload_before: dict[str, Any] = Field(default_factory=dict)
    payload_after: dict[str, Any] | None = None
    reviewer_decision: str | None = None
    reviewer_note: str | None = None
    status: Literal["pending", "resolved", "cancelled", "superseded", "stale"] = "pending"
    blocking: bool = True
    stage_output_version: int = 1
    superseded_by: str | None = None

    # Stage-advancement contract fields.
    action_contract_id: str = Field(default_factory=lambda: f"ACTC-{str(uuid.uuid4())[:8]}")
    action_schema_version: str = ACTION_SCHEMA_VERSION
    idempotency_key: str | None = None
    target_stage: int | None = None
    target_stage_version: int | None = None
    target_object_path: str | None = None
    expected_before_hash: str | None = None
    approved_payload_hash: str | None = None
    resume_token: str | None = None
    expires_at: datetime | None = None
    resolution_attempts: int = 0
    last_resolution_error: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None


class AuditEvent(BaseModel):
    """审计事件，用于记录人工监督与系统关键决策。"""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str
    actor: Literal["system", "user", "ai"]
    event_type: str
    target_type: str
    target_id: str
    before_hash: str | None = None
    after_hash: str | None = None
    before_snapshot: dict[str, Any] | None = None
    after_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ActionResolutionLog(BaseModel):
    """Append-only record for human action resolution attempts."""

    log_id: str = Field(default_factory=lambda: f"ARL-{str(uuid.uuid4())[:8]}")
    session_id: str
    action_id: str
    idempotency_key: str | None = None
    requested_status: str
    result_status: str
    before_hash: str | None = None
    after_hash: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ActionResolutionResult(BaseModel):
    """Action-resolution outcome.

    This is intentionally lightweight so API callers can understand whether a
    human action actually advanced the workflow, replayed an earlier decision,
    became stale, or failed contract validation.
    """

    session_id: str
    action_id: str
    requested_status: str
    result_status: Literal[
        "resolved",
        "idempotent_replay",
        "stale",
        "conflict",
        "validation_failed",
        "not_pending",
        "not_found",
        "error",
    ]
    action_status: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    # Explicit hash semantics for API/UI clients.
    action_hash: str | None = None
    payload_before_hash: str | None = None
    payload_after_hash: str | None = None
    log_id: str | None = None
    error_message: str | None = None
    can_continue: bool | None = None
    blockers_count: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LLMTrace(BaseModel):
    """Minimal GenAI trace for stage execution."""

    trace_id: str = Field(default_factory=lambda: f"TRC-{str(uuid.uuid4())[:8]}")
    session_id: str
    stage: int | None = None
    node_name: str = ""
    trace_type: Literal[
        "llm",
        "search",
        "parser",
        "gate",
        "action",
        "stage_operation",
        "eval",
        "report",
        "safety",
    ] = "llm"
    provider: str = "openai_compatible"
    model: str = ""
    prompt_template_id: str = ""
    prompt_template_version: str = "0.7.0"
    input_token_count: int | None = None
    output_token_count: int | None = None
    estimated_cost: float | None = None
    latency_ms: int | None = None
    retry_count: int = 0
    parser_status: str = "pending"
    safety_status: str = "not_scanned"
    evidence_count: int = 0
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# Human Oversight / Audit
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# 核心：会话上下文（LangGraph State）
# ─────────────────────────────────────────────

# Evidence 来源分类；tools.source_classifier.classify_source 也返回该类型，共用一处定义避免漂移。
SourceType = Literal[
    "official_doc",
    "paper",
    "github",
    "blog",
    "forum",
    "news",
    "unknown",
    "user_material",
]


class EvidenceSource(BaseModel):
    """可追溯证据来源。"""

    evidence_id: str = Field(default_factory=lambda: f"EVID-{str(uuid.uuid4())[:8]}")
    session_id: str
    title: str
    url: str | None = None
    source_type: SourceType = "unknown"
    credibility_score: float = 0.0
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str = ""
    claims: list[str] = Field(default_factory=list)
    used_by_failure_mode_ids: list[str] = Field(default_factory=list)
    verified: bool = False
    verified_by: str | None = None
    verified_at: datetime | None = None
    verification_note: str = ""


class SafetyFinding(BaseModel):
    """轻量安全扫描发现。"""

    finding_id: str = Field(default_factory=lambda: f"SAFE-{str(uuid.uuid4())[:8]}")
    session_id: str
    stage_id: int | None = None
    risk_type: Literal[
        "prompt_injection",
        "sensitive_info",
        "unsupported_claim",
        "over_autonomy",
        "unsafe_instruction",
        "source_untrusted",
        "policy_gap",
        "improper_output_handling",  # LLM05 (T2.1)
        "system_prompt_leakage",  # LLM07 (T2.1)
        "unbounded_consumption",  # LLM10 (T2.1)
    ]
    severity: Literal["low", "medium", "high", "critical"]
    location: str
    description: str
    recommended_action: str
    requires_human_review: bool = False
    status: Literal["open", "resolved", "dismissed"] = "open"

    # Taxonomy mapping fields. These default to empty/unknown so existing
    # context_json remains loadable without schema changes.
    taxonomy_refs: list[str] = Field(default_factory=list)
    control_refs: list[str] = Field(default_factory=list)
    mitigation_status: Literal["open", "mitigating", "mitigated", "accepted", "dismissed"] = "open"
    residual_risk: Literal["unknown", "low", "medium", "high", "critical"] = "unknown"

    resolution_note: str = ""
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvalCase(BaseModel):
    """可积累的压测 / 评估用例。

    从 Stage 3 结构化压测结果同步生成，暂不自动执行外部 eval runner。
    """

    eval_id: str = Field(default_factory=lambda: f"EVAL-{str(uuid.uuid4())[:8]}")
    session_id: str
    stage_id: int = 3
    target_node_id: str | None = None
    covered_failure_mode_ids: list[str] = Field(default_factory=list)
    scenario_type: Literal[
        "normal",
        "edge",
        "adversarial",
        "regression",
        "production_failure",
        "safety",
        "evidence",
        "parser",
    ] = "normal"
    source_type: Literal[
        "manual",
        "stage3_generated",
        "redteam_generated",
        "production_trace",
        "parser_error",
        "safety_finding",
        "imported",
    ] = "stage3_generated"
    source_trace_id: str | None = None
    source_ref_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    input_payload: str
    expected_behavior: str
    pass_criteria: list[str] = Field(default_factory=list)
    actual_output: str | None = None
    human_score: int | None = None
    human_comment: str | None = None
    passed: bool | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    scored_at: datetime | None = None


class EvalRun(BaseModel):
    """A single execution record for an EvalCase.

    EvalCase is the reusable test definition; EvalRun records one concrete run
    and links it to a dataset/experiment for regression tracking.
    """

    run_id: str = Field(default_factory=lambda: f"RUN-{str(uuid.uuid4())[:8]}")
    session_id: str
    eval_id: str
    dataset_id: str | None = None
    experiment_id: str | None = None
    target_node_id: str | None = None
    covered_failure_mode_ids: list[str] = Field(default_factory=list)
    stage_output_version: int = 1
    run_index: int | None = None
    run_mode: Literal["manual", "dry_run", "llm_node"] = "manual"
    input_payload: str
    expected_behavior: str
    pass_criteria: list[str] = Field(default_factory=list)
    actual_output: str | None = None
    judge_result: Literal["passed", "failed", "needs_review"] | None = None
    judge_reason: str = ""
    judge_mode: Literal["inherited", "rule", "llm", "human"] = "inherited"
    violated_criteria: list[str] = Field(default_factory=list)
    status: Literal["created", "running", "completed", "failed"] = "created"
    error_message: str = ""
    trace_id: str | None = None
    latency_ms: int | None = None
    estimated_cost: float | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class EvalJudgment(BaseModel):
    """Structured judge recommendation for one EvalRun.

    This is a recommendation layer. Gate decisions must not treat automated
    judge labels as a final human approval for high-risk cases.
    """

    judgment_id: str = Field(default_factory=lambda: f"JDG-{str(uuid.uuid4())[:8]}")
    session_id: str
    eval_run_id: str
    eval_id: str | None = None
    experiment_id: str | None = None
    judge_type: Literal["rule", "llm", "human_proxy"] = "rule"
    judge_model: str | None = None
    score: float | None = None
    label: Literal["passed", "failed", "needs_review"] = "needs_review"
    rationale: str = ""
    uncertainty: float | None = None
    cited_rules: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HumanCalibration(BaseModel):
    """Human override/calibration for an EvalRun judgment."""

    calibration_id: str = Field(default_factory=lambda: f"CAL-{str(uuid.uuid4())[:8]}")
    session_id: str
    eval_run_id: str
    eval_id: str | None = None
    experiment_id: str | None = None
    human_label: Literal["passed", "failed", "needs_review"]
    human_comment: str = ""
    judge_label: Literal["passed", "failed", "needs_review"] | None = None
    agreement: bool | None = None
    disagreement_reason: str = ""
    reviewer_id: str = "human_reviewer"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvalDataset(BaseModel):
    """Reusable grouping of EvalCase ids.

    Datasets are session-scoped. Cross-session workspace/project grouping is
    deferred to a future release.
    """

    dataset_id: str = Field(default_factory=lambda: f"DATASET-{str(uuid.uuid4())[:8]}")
    session_id: str
    name: str
    description: str = ""
    stage: int = 3
    scenario_type: Literal[
        "normal",
        "edge",
        "adversarial",
        "regression",
        "production_failure",
        "safety",
        "evidence",
        "parser",
        "mixed",
    ] = "mixed"
    version: str = "0.1"
    source: Literal[
        "manual",
        "stage3_generated",
        "imported",
        "production_trace",
        "redteam_generated",
    ] = "stage3_generated"
    owner: str = "system"
    case_ids: list[str] = Field(default_factory=list)
    baseline_experiment_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EvalAggregateMetrics(BaseModel):
    """Experiment-level aggregate metrics.

    Some fields are reserved for future trace/judge/redteam integration and
    default to zero/None until populated.
    """

    total_cases: int = 0
    run_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    needs_review_count: int = 0
    error_count: int = 0
    pass_rate: float = 0.0
    fail_rate: float = 0.0
    needs_review_rate: float = 0.0
    critical_fail_count: int = 0
    high_risk_fail_count: int = 0
    parser_failure_count: int = 0
    safety_violation_count: int = 0
    evidence_missing_count: int = 0
    hallucination_count: int = 0
    average_latency_ms: float | None = None
    estimated_total_cost: float | None = None
    scenario_counts: dict[str, int] = Field(default_factory=dict)
    target_node_counts: dict[str, int] = Field(default_factory=dict)
    failed_case_ids: list[str] = Field(default_factory=list)
    needs_review_case_ids: list[str] = Field(default_factory=list)

    # Judge/human calibration metrics.
    automated_judgment_count: int = 0
    human_calibration_count: int = 0
    human_disagreement_count: int = 0
    human_disagreement_rate: float | None = None
    human_final_label_count: int = 0


class EvalExperiment(BaseModel):
    """A repeatable run of an EvalDataset.

    Computes metrics and baseline comparison. Regression Gate blocking is enforced
    by EvalRegressionRule in core/gates/rules/eval_regression.py.
    """

    experiment_id: str = Field(default_factory=lambda: f"EXP-{str(uuid.uuid4())[:8]}")
    session_id: str
    dataset_id: str
    name: str
    description: str = ""
    status: Literal["created", "running", "completed", "failed", "cancelled"] = "created"
    provider: str | None = None
    model: str | None = None
    run_mode: Literal["manual", "dry_run", "llm_node"] = "manual"
    prompt_template_versions: dict[str, str] = Field(default_factory=dict)
    code_version: str | None = None
    run_config: dict[str, Any] = Field(default_factory=dict)
    run_config_hash: str | None = None
    eval_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    baseline_experiment_id: str | None = None
    aggregate_metrics: EvalAggregateMetrics = Field(default_factory=EvalAggregateMetrics)
    comparison_summary: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "system"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RedTeamCase(BaseModel):
    """Adversarial safety/eval case used by the Red Team gate.

    RedTeamCase is session-scoped. Cross-session workspace/project grouping is
    deferred to a future release. Approved cases link back into the EvalCase /
    EvalDataset / EvalExperiment regression pipeline.
    """

    redteam_case_id: str = Field(default_factory=lambda: f"RTC-{str(uuid.uuid4())[:8]}")
    session_id: str
    taxonomy_refs: list[str] = Field(default_factory=list)
    control_refs: list[str] = Field(default_factory=list)
    target_stage: int = 3
    target_node_id: str | None = None
    source_finding_id: str | None = None
    source_failure_mode_id: str | None = None
    attack_type: Literal[
        "direct_prompt_injection",
        "indirect_prompt_injection",
        "secret_exfiltration",
        "fake_citation",
        "source_poisoning",
        "tool_overreach",
        "excessive_agency",
        "policy_bypass",
        "evaluator_gaming",
        "unsafe_autonomy",
        "unsupported_claim",
    ] = "unsupported_claim"
    prompt: str
    malicious_material: str = ""
    expected_failure_mode: str
    expected_safe_behavior: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    status: Literal["draft", "approved", "rejected", "synced_to_eval"] = "draft"
    generated_by: Literal["system", "human", "llm"] = "system"
    linked_eval_case_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: datetime | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InterruptRecord(BaseModel):
    """Business-level mapping between a human action and an interrupt point.

    PendingHumanAction remains the product/business approval contract.
    InterruptRecord is the execution-engine mapping layer used by the
    experimental LangGraph interrupt/checkpoint adapter (langgraph_interrupt mode).
    """

    interrupt_id: str = Field(default_factory=lambda: f"INT-{str(uuid.uuid4())[:8]}")
    session_id: str
    action_id: str
    stage_id: int
    stage_output_version: int = 1
    status: Literal["pending", "resumed", "cancelled"] = "pending"
    resume_value: dict[str, Any] | None = None

    # Adapter metadata. These fields are nullable so existing context_json rows
    # and lightweight SQL tables remain backward-compatible.
    thread_id: str | None = None
    node_name: str | None = None
    checkpoint_ns: str | None = None
    interrupt_payload: dict[str, Any] | None = None
    resume_consumed_at: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None


class ReportArtifact(BaseModel):
    """版本化报告快照，后续可扩展为独立 report_artifacts 表。"""

    report_id: str = Field(default_factory=lambda: f"RPT-{str(uuid.uuid4())[:8]}")
    session_id: str
    version: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    ai_generated: dict[str, Any] = Field(default_factory=dict)
    human_reviewed: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    open_risks: list[dict[str, Any]] = Field(default_factory=list)
    eval_summary: dict[str, Any] = Field(default_factory=dict)
    eval_runs: list[dict[str, Any]] = Field(default_factory=list)
    failed_eval_runs: list[dict[str, Any]] = Field(default_factory=list)
    content_json: dict[str, Any] = Field(default_factory=dict)
    content_markdown: str = ""


class ProjectContext(BaseModel):
    """
    贯穿整个 LangGraph 流程的核心状态对象。
    所有节点只读取、增量更新此对象，不得引入外部状态。
    """

    # 元信息
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    current_state: SessionState = SessionState.INIT
    # 多租户：session 所属 tenant_id，由 session_store.load() 填充，保存时写入 sessions 表
    tenant_id: str = ""
    selected_scenario_id: str | None = None
    scenario_name: str | None = None
    scenario_description: str = ""
    scenario_config: dict[str, Any] = Field(default_factory=dict)

    # ── Context schema migration metadata ─────────
    context_schema_version: str = CONTEXT_SCHEMA_VERSION
    migration_history: list[MigrationRecord] = Field(default_factory=list)
    last_migrated_at: datetime | None = None
    migration_warnings: list[str] = Field(default_factory=list)

    # ── 用户原始输入（INIT 阶段收集）────────────────
    research_target: str = ""  # 研究对象（如：GPT-4o）
    domain: str = ""  # 具体领域（如：法律文书生成）
    goal: str = ""  # 具体目标（如：提高合同起草准确率）
    user_materials: list[str] = Field(default_factory=list)  # 人工补充资料

    # ── 数据分类分级（DSL 21 条 / PIPL 51 条）────────
    data_classification: Literal["public_demo", "business_internal", "sensitive_personal"] = (
        "business_internal"
    )

    # ── 各阶段结构化输出（逐步填充）────────────────
    stage_1_output: Stage1Output | None = None
    stage_2_output: Stage2Output | None = None
    stage_3_output: Stage3Output | None = None
    stage_4_output: Stage4Output | None = None

    # ── 对话历史（按阶段分段）──────────────────────
    # key: "stage_0"(init) | "stage_1" | "stage_2" | "stage_3" | "stage_4"
    conversation_history: dict[str, list[Message]] = Field(default_factory=dict)

    # ── 人工审核记录 ────────────────────────────────
    review_notes: dict[str, str] = Field(default_factory=dict)
    # key: "stage_1" | "stage_2" | "stage_3" | "stage_4"

    # ── 【需核验】追踪 ──────────────────────────────
    flagged_items: list[FlaggedItem] = Field(default_factory=list)

    # ── Human Oversight / Audit ─────────────────────
    pending_actions: list[PendingHumanAction] = Field(default_factory=list)
    audit_events: list[AuditEvent] = Field(default_factory=list)
    action_resolution_logs: list[ActionResolutionLog] = Field(default_factory=list)
    llm_traces: list[LLMTrace] = Field(default_factory=list)
    reviewed_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parser_errors: dict[str, str] = Field(default_factory=dict)
    stage_output_versions: dict[str, int] = Field(default_factory=dict)
    # key: "stage_2" -> {"stage_1": 3}; records upstream versions used to generate each output.
    stage_dependency_versions: dict[str, dict[str, int]] = Field(default_factory=dict)
    # key: "stage_3" -> stale metadata; used to block downstream advancement after upstream edits.
    stage_staleness: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # ── Evidence / Safety / Reports ─────────────────
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)
    safety_findings: list[SafetyFinding] = Field(default_factory=list)
    report_artifacts: list[ReportArtifact] = Field(default_factory=list)
    eval_cases: list[EvalCase] = Field(default_factory=list)
    eval_runs: list[EvalRun] = Field(default_factory=list)
    eval_judgments: list[EvalJudgment] = Field(default_factory=list)
    human_calibrations: list[HumanCalibration] = Field(default_factory=list)
    eval_datasets: list[EvalDataset] = Field(default_factory=list)
    eval_experiments: list[EvalExperiment] = Field(default_factory=list)
    redteam_cases: list[RedTeamCase] = Field(default_factory=list)
    interrupt_records: list[InterruptRecord] = Field(default_factory=list)

    # ── 迭代控制 ────────────────────────────────────
    iteration_count: int = 0
    max_iterations: int = 3  # 单阶段最大回退次数，超出则强制提示用户

    # ── LLM 用量计数（T2.1 LLM10 Unbounded Consumption）────────
    llm_call_count: int = 0
    llm_token_estimate: int = 0

    # ── 错误信息 ────────────────────────────────────
    last_error: str | None = None

    def get_stage_history(self, stage: int) -> list[Message]:
        return self.conversation_history.get(f"stage_{stage}", [])

    def append_message(self, stage: int, message: Message) -> None:
        key = f"stage_{stage}"
        if key not in self.conversation_history:
            self.conversation_history[key] = []
        self.conversation_history[key].append(message)
        self.updated_at = datetime.utcnow()

    def get_pending_flags(self) -> list[FlaggedItem]:
        return [f for f in self.flagged_items if f.status == FlagStatus.PENDING]

    def get_pending_actions(self, stage: int | None = None) -> list[PendingHumanAction]:
        """返回尚未处理的人工监督动作。"""
        actions = [a for a in self.pending_actions if a.status == HumanActionStatus.PENDING.value]
        if stage is not None:
            actions = [a for a in actions if a.stage_id == stage]
        return actions

    def has_blocking_actions(self, stage: int | None = None) -> bool:
        """当前会话/阶段是否仍存在阻断推进的人工动作。"""
        return any(action.blocking for action in self.get_pending_actions(stage))

    def to_context_summary(self) -> str:
        """生成跨阶段注入的上下文摘要"""
        lines = [
            "## 项目背景（全程约束）",
            f"- 研究对象：{self.research_target}",
            f"- 具体领域：{self.domain}",
            f"- 具体目标：{self.goal}",
        ]
        if self.stage_1_output:
            lines.append("\n## 阶段一：已识别失败模式")
            for fm in self.stage_1_output.failure_modes:
                lines.append(f"  - {fm.id} [{fm.severity.upper()}] {fm.category}：{fm.description}")
            lines.append(f"\n  直接结论：{self.stage_1_output.direct_conclusion}")

        if self.stage_2_output:
            lines.append("\n## 阶段二：工作流设计")
            for node in self.stage_2_output.workflow_nodes:
                lines.append(f"  - {node.node_id} {node.stage_name}（{node.model_assigned}）")

        if self.stage_3_output:
            passed = "通过" if self.stage_3_output.overall_passed else "未通过"
            lines.append(f"\n## 阶段三：压测结果（{passed}）")

        return "\n".join(lines)

    pending_input: str = ""  # 当前轮次待处理的用户输入，节点执行后清空
