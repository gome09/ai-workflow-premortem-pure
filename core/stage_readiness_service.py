# core/stage_readiness_service.py
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.models import HumanActionStatus, PendingHumanAction, ProjectContext
from core.stage_scope_service import actionable_stage_ids, current_stage_id, is_stage_actionable

BlockerType = Literal[
    "missing_stage_output",
    "stale_dependency",
    "pending_action",
    "rejected_action",
    "unresolved_escalation",
    "parser_error",
    "safety_finding",
    "evidence_gap",
    "policy_gap",
    "eval_failure",
    "redteam_coverage",
    "eval_regression",
    "trace_backfill_gap",
    "final_governance",
]

# Keep this Literal synchronized with
# core.stage_advancement_contract.REQUIRED_RESOLUTIONS.  Alpha.10 closes the
# drift where Eval Regression rules could emit concrete required_resolution
# values that StageBlocker did not accept.
RequiredResolution = Literal[
    "run_stage",
    "rerun_stage",
    "resolve_action",
    "verify_evidence",
    "edit_stage_output",
    "revise_stage",
    "back_stage",
    "approve_escalation",
    "resolve_safety_finding",
    "create_eval_dataset_from_stage3",
    "add_eval_cases_to_dataset",
    "set_eval_baseline",
    "create_eval_experiment",
    "run_eval_experiment",
    "compare_eval_experiment",
    "generate_redteam_cases",
    "approve_redteam_case",
    "sync_redteam_eval_case",
    "create_redteam_dataset",
    "trace_to_eval_case",
    "create_trace_backfill_dataset",
]

Severity = Literal["low", "medium", "high", "critical"]
StageLifecycle = Literal[
    "not_started", "running", "review", "blocked", "ready_to_advance", "approved", "stale"
]


class StageBlocker(BaseModel):
    """Structured reason why a stage cannot advance.

    PendingHumanAction remains the authoritative human-action contract.
    StageBlocker is the read-only stage-advancement contract used by the
    transition policy, API, report, and frontend so they explain the same gate.
    """

    blocker_id: str
    stage_id: int
    stage_output_version: int
    blocker_type: BlockerType
    rule_id: str = ""
    severity: Severity = "medium"
    message: str
    source_type: str | None = None
    source_id: str | None = None
    action_id: str | None = None
    required_resolution: RequiredResolution
    can_be_overridden_by_approval: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class StageGateResult(BaseModel):
    """Machine-readable result for one stage gate evaluation."""

    stage_id: int
    stage_output_version: int
    can_continue: bool
    blockers: list[StageBlocker] = Field(default_factory=list)


class StageReadiness(BaseModel):
    """Read-only view consumed by API/frontend/report."""

    stage_id: int
    state: str
    stage_output_exists: bool
    stage_output_version: int
    stage_lifecycle: StageLifecycle = "not_started"
    can_continue: bool
    block_reason: str = ""
    blockers: list[StageBlocker] = Field(default_factory=list)
    pending_action_ids: list[str] = Field(default_factory=list)
    pending_blocking_action_ids: list[str] = Field(default_factory=list)
    open_safety_finding_ids: list[str] = Field(default_factory=list)
    parser_error: str = ""
    recommended_next_operations: list[str] = Field(default_factory=list)
    stage_dependency_versions: dict[str, int] = Field(default_factory=dict)
    stale_reason: str = ""
    stage_metadata: dict[str, Any] = Field(default_factory=dict)
    is_actionable: bool = True
    future_stage: bool = False
    visibility_reason: str = ""


def _dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _current_version(ctx: ProjectContext, stage: int) -> int:
    return int(ctx.stage_output_versions.get(f"stage_{stage}", 1))


def _stage_output_exists(ctx: ProjectContext, stage: int) -> bool:
    return getattr(ctx, f"stage_{stage}_output", None) is not None


def _stage_key(stage: int) -> str:
    return f"stage_{stage}"


def _stage_state_value(ctx: ProjectContext) -> str:
    return getattr(ctx.current_state, "value", str(ctx.current_state))


def _stage_state_index(state_value: str) -> int:
    order = [
        "init",
        "s1_running",
        "s1_review",
        "s2_running",
        "s2_review",
        "s3_running",
        "s3_review",
        "s4_running",
        "s4_review",
        "complete",
    ]
    try:
        return order.index(state_value)
    except ValueError:
        return -1


def _stage_review_index(stage: int) -> int:
    return _stage_state_index(f"s{stage}_review")


def _collect_missing_output_blockers(ctx: ProjectContext, stage: int) -> list[StageBlocker]:
    if _stage_output_exists(ctx, stage):
        return []
    return [
        _blocker(
            ctx=ctx,
            stage=stage,
            blocker_type="missing_stage_output",
            severity="medium",
            message=f"阶段{stage}尚未生成结构化输出，不能进入下一阶段。",
            source_type="stage",
            source_id=_stage_key(stage),
            required_resolution="run_stage",
            can_be_overridden_by_approval=False,
        )
    ]


def _collect_stale_dependency_blockers(ctx: ProjectContext, stage: int) -> list[StageBlocker]:
    if not _stage_output_exists(ctx, stage):
        return []

    key = _stage_key(stage)
    blockers: list[StageBlocker] = []
    stale_meta = getattr(ctx, "stage_staleness", {}).get(key) or {}
    if stale_meta.get("stale"):
        blockers.append(
            _blocker(
                ctx=ctx,
                stage=stage,
                blocker_type="stale_dependency",
                severity="high",
                message=(
                    f"阶段{stage}输出已过期：{stale_meta.get('reason') or '上游阶段已更新'}。"
                    "请重跑该阶段后再继续。"
                ),
                source_type="stage",
                source_id=key,
                required_resolution="rerun_stage",
                can_be_overridden_by_approval=False,
                metadata=stale_meta,
            )
        )

    dependency_versions = getattr(ctx, "stage_dependency_versions", {}).get(key, {}) or {}
    stale_dependencies: dict[str, dict[str, int]] = {}
    for upstream_key, recorded_version in dependency_versions.items():
        current_version = int(ctx.stage_output_versions.get(upstream_key, 1))
        if current_version > int(recorded_version):
            stale_dependencies[upstream_key] = {
                "recorded_version": int(recorded_version),
                "current_version": current_version,
            }

    if stale_dependencies:
        blockers.append(
            _blocker(
                ctx=ctx,
                stage=stage,
                blocker_type="stale_dependency",
                severity="high",
                message=f"阶段{stage}依赖的上游输出版本已更新，请重跑阶段{stage}。",
                source_type="stage_dependency_versions",
                source_id=key,
                required_resolution="rerun_stage",
                can_be_overridden_by_approval=False,
                metadata={"stale_dependencies": stale_dependencies},
            )
        )
    return blockers


def _stage_lifecycle(ctx: ProjectContext, stage: int, result: StageGateResult) -> StageLifecycle:
    key = _stage_key(stage)
    state_value = _stage_state_value(ctx)
    if getattr(ctx, "stage_staleness", {}).get(key, {}).get("stale"):
        return "stale"
    if state_value == f"s{stage}_running":
        return "running"
    if not _stage_output_exists(ctx, stage):
        return "not_started"
    if state_value == f"s{stage}_review":
        return "ready_to_advance" if result.can_continue else "blocked"
    if _stage_state_index(state_value) > _stage_review_index(stage):
        return "approved" if result.can_continue else "blocked"
    return "review" if result.can_continue else "blocked"


def _current_stage_actions(ctx: ProjectContext, stage: int) -> list[PendingHumanAction]:
    current_version = _current_version(ctx, stage)
    return [
        action
        for action in ctx.pending_actions
        if action.stage_id == stage and action.stage_output_version == current_version
    ]


def _has_resolved_source_action(
    ctx: ProjectContext,
    stage: int,
    *,
    source_type: str,
    source_id: str,
    decisions: set[str] | None = None,
) -> bool:
    for action in _current_stage_actions(ctx, stage):
        if action.source_type != source_type or action.source_id != source_id:
            continue
        if action.status != HumanActionStatus.RESOLVED.value:
            continue
        if decisions is not None and action.reviewer_decision not in decisions:
            continue
        return True
    return False


def _find_action_id(
    ctx: ProjectContext,
    stage: int,
    *,
    source_type: str | None = None,
    source_id: str | None = None,
    statuses: set[str] | None = None,
) -> str | None:
    for action in _current_stage_actions(ctx, stage):
        if source_type is not None and action.source_type != source_type:
            continue
        if source_id is not None and action.source_id != source_id:
            continue
        if statuses is not None and action.status not in statuses:
            continue
        return action.action_id
    return None


def _find_pending_action_id(
    ctx: ProjectContext,
    stage: int,
    *,
    source_type: str | None = None,
    source_id: str | None = None,
) -> str | None:
    """Return only an executable pending action binding.

    StageResolutionOperation.api_path must never point at a resolved,
    cancelled, or superseded action because /actions/{action_id}/resolve rejects
    non-pending actions. Historical action ids are exposed separately in blocker
    metadata for audit/debugging only.
    """
    return _find_action_id(
        ctx,
        stage,
        source_type=source_type,
        source_id=source_id,
        statuses={HumanActionStatus.PENDING.value},
    )


def _find_historical_action_ids(
    ctx: ProjectContext,
    stage: int,
    *,
    source_type: str | None = None,
    source_id: str | None = None,
) -> list[str]:
    ids: list[str] = []
    for action in _current_stage_actions(ctx, stage):
        if source_type is not None and action.source_type != source_type:
            continue
        if source_id is not None and action.source_id != source_id:
            continue
        if action.status == HumanActionStatus.PENDING.value:
            continue
        ids.append(action.action_id)
    return ids


def _with_action_history(
    metadata: dict[str, Any] | None,
    *,
    ctx: ProjectContext,
    stage: int,
    source_type: str | None = None,
    source_id: str | None = None,
    pending_action_id: str | None = None,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    historical = _find_historical_action_ids(
        ctx, stage, source_type=source_type, source_id=source_id
    )
    if historical:
        merged["historical_action_ids"] = historical
    merged["pending_action_id"] = pending_action_id
    merged["api_binding_available"] = bool(pending_action_id)
    return merged


def _safe_token(value: str | None) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "none").strip("_")
    return token[:80] or "none"


def _blocker(
    *,
    ctx: ProjectContext,
    stage: int,
    blocker_type: BlockerType,
    message: str,
    severity: Severity = "medium",
    source_type: str | None = None,
    source_id: str | None = None,
    action_id: str | None = None,
    required_resolution: RequiredResolution = "resolve_action",
    can_be_overridden_by_approval: bool = False,
    metadata: dict[str, Any] | None = None,
) -> StageBlocker:
    version = _current_version(ctx, stage)
    raw_id = f"S{stage}_V{version}_{blocker_type}_{source_type or 'stage'}_{source_id or action_id or 'gate'}"
    return StageBlocker(
        blocker_id=_safe_token(raw_id),
        stage_id=stage,
        stage_output_version=version,
        blocker_type=blocker_type,
        severity=severity,
        message=message,
        source_type=source_type,
        source_id=source_id,
        action_id=action_id,
        required_resolution=required_resolution,
        can_be_overridden_by_approval=can_be_overridden_by_approval,
        metadata=metadata or {},
    )


def _high_risk_node_ids(ctx: ProjectContext) -> set[str]:
    if not ctx.stage_1_output or not ctx.stage_2_output:
        return set()
    high_risk_failure_modes = {
        fm.id
        for fm in ctx.stage_1_output.failure_modes
        if str(fm.severity).lower() in {"high", "critical"}
    }
    return {
        node.node_id
        for node in ctx.stage_2_output.workflow_nodes
        if high_risk_failure_modes.intersection(set(node.failure_modes_addressed or []))
    }


def _stage_2_coverage_matrix(ctx: ProjectContext) -> list[dict[str, Any]]:
    if not ctx.stage_1_output:
        return []
    nodes = ctx.stage_2_output.workflow_nodes if ctx.stage_2_output else []
    rows: list[dict[str, Any]] = []
    for fm in ctx.stage_1_output.failure_modes:
        if str(fm.severity).lower() not in {"high", "critical"}:
            continue
        covering_nodes = [
            node for node in nodes if fm.id in set(node.failure_modes_addressed or [])
        ]
        rows.append(
            {
                "failure_mode_id": fm.id,
                "severity": fm.severity,
                "covering_node_ids": [node.node_id for node in covering_nodes],
                "oversight_policy_ids": [
                    getattr(node.oversight_policy, "policy_id", None)
                    for node in covering_nodes
                    if node.oversight_policy is not None
                ],
                "nodes_missing_policy": [
                    node.node_id for node in covering_nodes if node.oversight_policy is None
                ],
            }
        )
    return rows


def _stage_3_coverage_warning(ctx: ProjectContext) -> dict[str, Any]:
    high_risk_nodes = _high_risk_node_ids(ctx)
    eval_nodes = {case.target_node_id for case in ctx.eval_cases if case.target_node_id}
    run_nodes = {run.target_node_id for run in ctx.eval_runs if run.target_node_id}
    covered = eval_nodes.union(run_nodes)
    missing = sorted(high_risk_nodes - eval_nodes)
    return {
        "high_risk_node_ids": sorted(high_risk_nodes),
        "covered_node_ids": sorted(high_risk_nodes.intersection(covered)),
        "eval_case_covered_node_ids": sorted(high_risk_nodes.intersection(eval_nodes)),
        "eval_run_node_ids": sorted(high_risk_nodes.intersection(run_nodes)),
        "missing_eval_coverage_node_ids": missing,
        "coverage_warning": bool(missing),
        "blocking": bool(missing),
        "blocking_reason": "High-risk workflow nodes must be covered by Stage 3 EvalCase records.",
    }


def _collect_action_state_blockers(ctx: ProjectContext, stage: int) -> list[StageBlocker]:
    version = _current_version(ctx, stage)
    inactive = {HumanActionStatus.CANCELLED.value, HumanActionStatus.SUPERSEDED.value}
    blockers: list[StageBlocker] = []

    for action in ctx.pending_actions:
        if action.stage_id != stage or action.stage_output_version != version:
            continue
        if action.status == HumanActionStatus.PENDING.value and action.blocking:
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="pending_action",
                    severity=action.risk_level,
                    message=(
                        f"阶段{stage} v{version} 仍有阻断型人工动作未处理："
                        f"{action.action_id} ({action.action_type})。"
                    ),
                    source_type=action.source_type or "human_action",
                    source_id=action.source_id,
                    action_id=action.action_id,
                    required_resolution=(
                        "approve_escalation"
                        if action.action_type == "escalate"
                        else "resolve_action"
                    ),
                    can_be_overridden_by_approval=False,
                    metadata={
                        "action_type": action.action_type,
                        "title": action.title,
                        "trigger_reason": action.trigger_reason,
                    },
                )
            )
            continue

        if (
            action.status == HumanActionStatus.RESOLVED.value
            and action.reviewer_decision == "reject"
            and action.action_type in {"approve", "edit", "escalate"}
        ):
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="rejected_action",
                    severity=action.risk_level,
                    message=(
                        f"阶段{stage} v{version} 存在被驳回的关键动作："
                        f"{action.action_id}。需要修改或回退后再继续。"
                    ),
                    source_type=action.source_type or "human_action",
                    source_id=action.source_id,
                    action_id=action.action_id,
                    required_resolution="revise_stage",
                    can_be_overridden_by_approval=False,
                    metadata={"reviewer_decision": action.reviewer_decision},
                )
            )
            continue

        if (
            action.action_type == "escalate"
            and not (
                action.status == HumanActionStatus.RESOLVED.value
                and action.reviewer_decision == "approve"
            )
            and action.status not in inactive
        ):
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="unresolved_escalation",
                    severity=action.risk_level,
                    message=(
                        f"阶段{stage} v{version} 存在未明确批准的升级风险：{action.action_id}。"
                    ),
                    source_type=action.source_type or "human_action",
                    source_id=action.source_id,
                    action_id=action.action_id,
                    required_resolution="approve_escalation",
                    can_be_overridden_by_approval=False,
                )
            )
    return blockers


def _collect_parser_blockers(ctx: ProjectContext, stage: int) -> list[StageBlocker]:
    key = f"stage_{stage}"
    error = ctx.parser_errors.get(key)
    if not error:
        return []
    action_id = _find_pending_action_id(ctx, stage, source_type="parser", source_id=key)
    return [
        _blocker(
            ctx=ctx,
            stage=stage,
            blocker_type="parser_error",
            severity="high",
            message=f"阶段{stage}存在结构化解析错误，需要提交结构化 edit 动作修复后才能继续。",
            source_type="parser",
            source_id=key,
            action_id=action_id,
            required_resolution="edit_stage_output",
            can_be_overridden_by_approval=False,
            metadata=_with_action_history(
                {
                    "parser_error": error,
                    "requires_structured_output": True,
                    "expected_schema": f"Stage{stage}Schema",
                },
                ctx=ctx,
                stage=stage,
                source_type="parser",
                source_id=key,
                pending_action_id=action_id,
            ),
        )
    ]


def _collect_safety_blockers(ctx: ProjectContext, stage: int) -> list[StageBlocker]:
    blockers: list[StageBlocker] = []
    for finding in ctx.safety_findings:
        if finding.stage_id != stage:
            continue
        if finding.status != "open" or not finding.requires_human_review:
            continue
        if finding.severity not in {"high", "critical"}:
            continue
        action_id = _find_pending_action_id(
            ctx, stage, source_type="safety_finding", source_id=finding.finding_id
        )
        blockers.append(
            _blocker(
                ctx=ctx,
                stage=stage,
                blocker_type="safety_finding",
                severity=finding.severity,
                message=(
                    f"阶段{stage}仍有 {finding.severity} 安全发现未关闭：{finding.finding_id}。"
                ),
                source_type="safety_finding",
                source_id=finding.finding_id,
                action_id=action_id,
                required_resolution="resolve_safety_finding"
                if action_id is None
                else "resolve_action",
                can_be_overridden_by_approval=True,
                metadata=_with_action_history(
                    {
                        "risk_type": finding.risk_type,
                        "recommended_action": finding.recommended_action,
                    },
                    ctx=ctx,
                    stage=stage,
                    source_type="safety_finding",
                    source_id=finding.finding_id,
                    pending_action_id=action_id,
                ),
            )
        )
    return blockers


def _collect_stage1_evidence_blockers(ctx: ProjectContext) -> list[StageBlocker]:
    if not ctx.stage_1_output:
        return []
    evidence_by_id = {ev.evidence_id: ev for ev in ctx.evidence_sources}
    blockers: list[StageBlocker] = []
    for fm in ctx.stage_1_output.failure_modes:
        severity = str(fm.severity).lower()
        if severity not in {"high", "critical"}:
            continue
        evidence_ids = list(dict.fromkeys(getattr(fm, "evidence_ids", []) or []))
        if not evidence_ids:
            action_id = _find_pending_action_id(ctx, 1, source_type="evidence_gap", source_id=fm.id)
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=1,
                    blocker_type="evidence_gap",
                    severity=fm.severity,
                    message=f"阶段1高风险失败模式 {fm.id} 缺少 evidence_id，必须编辑结构化 Stage1 输出补充证据引用。",
                    source_type="failure_mode",
                    source_id=fm.id,
                    action_id=action_id,
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata=_with_action_history(
                        {
                            "gap_type": "missing_evidence_id",
                            "requires_structured_output": True,
                            "expected_schema": "Stage1Schema",
                        },
                        ctx=ctx,
                        stage=1,
                        source_type="evidence_gap",
                        source_id=fm.id,
                        pending_action_id=action_id,
                    ),
                )
            )
            continue

        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                action_id = _find_pending_action_id(
                    ctx, 1, source_type="evidence_gap", source_id=fm.id
                )
                blockers.append(
                    _blocker(
                        ctx=ctx,
                        stage=1,
                        blocker_type="evidence_gap",
                        severity=fm.severity,
                        message=(
                            f"阶段1高风险失败模式 {fm.id} 引用了不存在的证据 {evidence_id}，"
                            "必须编辑结构化 Stage1 输出，不能调用 evidence verify。"
                        ),
                        source_type="failure_mode",
                        source_id=fm.id,
                        action_id=action_id,
                        required_resolution="edit_stage_output",
                        can_be_overridden_by_approval=False,
                        metadata=_with_action_history(
                            {
                                "gap_type": "unknown_evidence_id",
                                "missing_evidence_id": evidence_id,
                                "requires_structured_output": True,
                                "expected_schema": "Stage1Schema",
                            },
                            ctx=ctx,
                            stage=1,
                            source_type="evidence_gap",
                            source_id=fm.id,
                            pending_action_id=action_id,
                        ),
                    )
                )
                continue

            if getattr(evidence, "verified", False):
                continue

            action_id = None
            for source_type in {"evidence_unverified_for_high_risk", "evidence_low_credibility"}:
                action_id = _find_pending_action_id(
                    ctx, 1, source_type=source_type, source_id=fm.id
                )
                if action_id:
                    break
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=1,
                    blocker_type="evidence_gap",
                    severity=fm.severity,
                    message=(
                        f"阶段1高风险失败模式 {fm.id} 引用的证据 {evidence_id} "
                        "尚未 verified。dismiss action 只会关闭动作，不会解除该证据门控。"
                    ),
                    source_type="evidence",
                    source_id=evidence_id,
                    action_id=action_id,
                    required_resolution="verify_evidence",
                    can_be_overridden_by_approval=False,
                    metadata=_with_action_history(
                        {
                            "gap_type": "unverified_evidence_id",
                            "failure_mode_id": fm.id,
                            "evidence_exists": True,
                            "source_type": getattr(evidence, "source_type", None),
                            "credibility_score": getattr(evidence, "credibility_score", None),
                        },
                        ctx=ctx,
                        stage=1,
                        source_type="evidence_unverified_for_high_risk",
                        source_id=fm.id,
                        pending_action_id=action_id,
                    ),
                )
            )
    return blockers


def _collect_stage2_policy_blockers(ctx: ProjectContext) -> list[StageBlocker]:
    if not ctx.stage_1_output or not ctx.stage_2_output:
        return []

    high_risk_ids = {
        fm.id
        for fm in ctx.stage_1_output.failure_modes
        if str(fm.severity).lower() in {"high", "critical"}
    }
    if not high_risk_ids:
        return []

    covered: set[str] = set()
    blockers: list[StageBlocker] = []
    severity_by_fm = {
        fm.id: fm.severity
        for fm in ctx.stage_1_output.failure_modes
        if str(fm.severity).lower() in {"high", "critical"}
    }

    for node in ctx.stage_2_output.workflow_nodes:
        addressed = set(node.failure_modes_addressed or [])
        high_risk_addressed = addressed.intersection(high_risk_ids)
        covered.update(high_risk_addressed)
        if high_risk_addressed and node.oversight_policy is None:
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=2,
                    blocker_type="policy_gap",
                    severity="high",
                    message=(
                        f"阶段2节点 {node.node_id} 覆盖高风险 failure_mode "
                        f"{', '.join(sorted(high_risk_addressed))}，但缺少 HumanOversightPolicy。"
                    ),
                    source_type="workflow_node",
                    source_id=node.node_id,
                    action_id=_find_pending_action_id(
                        ctx, 2, source_type="policy_gap", source_id=node.node_id
                    ),
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata=_with_action_history(
                        {
                            "failure_mode_ids": sorted(high_risk_addressed),
                            "requires_structured_output": True,
                            "expected_schema": "Stage2Schema",
                        },
                        ctx=ctx,
                        stage=2,
                        source_type="policy_gap",
                        source_id=node.node_id,
                        pending_action_id=_find_pending_action_id(
                            ctx, 2, source_type="policy_gap", source_id=node.node_id
                        ),
                    ),
                )
            )

    for failure_mode_id in sorted(high_risk_ids - covered):
        blockers.append(
            _blocker(
                ctx=ctx,
                stage=2,
                blocker_type="policy_gap",
                severity=severity_by_fm.get(failure_mode_id, "high"),
                message=f"阶段2没有 workflow node 覆盖高风险 failure_mode：{failure_mode_id}。",
                source_type="failure_mode",
                source_id=failure_mode_id,
                action_id=_find_pending_action_id(
                    ctx, 2, source_type="policy_gap", source_id=failure_mode_id
                ),
                required_resolution="edit_stage_output",
                can_be_overridden_by_approval=False,
                metadata=_with_action_history(
                    {
                        "gap_type": "uncovered_high_risk_failure_mode",
                        "requires_structured_output": True,
                        "expected_schema": "Stage2Schema",
                    },
                    ctx=ctx,
                    stage=2,
                    source_type="policy_gap",
                    source_id=failure_mode_id,
                    pending_action_id=_find_pending_action_id(
                        ctx, 2, source_type="policy_gap", source_id=failure_mode_id
                    ),
                ),
            )
        )
    return blockers


def _collect_stage3_eval_blockers(ctx: ProjectContext) -> list[StageBlocker]:
    high_risk_nodes = _high_risk_node_ids(ctx)
    if not high_risk_nodes:
        return []

    blockers: list[StageBlocker] = []
    eval_case_nodes = {case.target_node_id for case in ctx.eval_cases if case.target_node_id}
    for node_id in sorted(high_risk_nodes - eval_case_nodes):
        blockers.append(
            _blocker(
                ctx=ctx,
                stage=3,
                blocker_type="eval_failure",
                severity="high",
                message=f"阶段3高风险节点 {node_id} 缺少 EvalCase 覆盖，不能仅作为提醒放行。",
                source_type="eval_coverage",
                source_id=node_id,
                action_id=_find_pending_action_id(
                    ctx, 3, source_type="eval_coverage", source_id=node_id
                ),
                required_resolution="edit_stage_output",
                can_be_overridden_by_approval=False,
                metadata=_with_action_history(
                    {
                        "target_node_id": node_id,
                        "gap_type": "missing_eval_case_coverage",
                        "expected_schema": "Stage3Schema",
                        "requires_structured_output": True,
                    },
                    ctx=ctx,
                    stage=3,
                    source_type="eval_coverage",
                    source_id=node_id,
                    pending_action_id=_find_pending_action_id(
                        ctx, 3, source_type="eval_coverage", source_id=node_id
                    ),
                ),
            )
        )

    for case in ctx.eval_cases:
        if case.passed is not False or case.target_node_id not in high_risk_nodes:
            continue
        if _has_resolved_source_action(
            ctx,
            3,
            source_type="eval_case",
            source_id=case.eval_id,
            decisions={"approve", "edit"},
        ):
            continue
        blockers.append(
            _blocker(
                ctx=ctx,
                stage=3,
                blocker_type="eval_failure",
                severity="high",
                message=f"阶段3高风险节点 {case.target_node_id} 的 EvalCase {case.eval_id} 失败且未处理。",
                source_type="eval_case",
                source_id=case.eval_id,
                action_id=_find_pending_action_id(
                    ctx, 3, source_type="eval_case", source_id=case.eval_id
                ),
                required_resolution="resolve_action",
                can_be_overridden_by_approval=True,
                metadata=_with_action_history(
                    {"target_node_id": case.target_node_id, "scenario_type": case.scenario_type},
                    ctx=ctx,
                    stage=3,
                    source_type="eval_case",
                    source_id=case.eval_id,
                    pending_action_id=_find_pending_action_id(
                        ctx, 3, source_type="eval_case", source_id=case.eval_id
                    ),
                ),
            )
        )

    for run in ctx.eval_runs:
        failed = run.status == "failed" or run.judge_result == "failed"
        needs_review = run.judge_result == "needs_review"
        if not (failed or needs_review) or run.target_node_id not in high_risk_nodes:
            continue
        if _has_resolved_source_action(
            ctx,
            3,
            source_type="eval_run",
            source_id=run.run_id,
            decisions={"approve", "edit"},
        ):
            continue
        blockers.append(
            _blocker(
                ctx=ctx,
                stage=3,
                blocker_type="eval_failure",
                severity="high",
                message=(
                    f"阶段3高风险节点 {run.target_node_id} 的 EvalRun {run.run_id} "
                    f"{'需要人工复核' if needs_review and not failed else '失败'}且未处理。"
                ),
                source_type="eval_run",
                source_id=run.run_id,
                action_id=_find_pending_action_id(
                    ctx, 3, source_type="eval_run", source_id=run.run_id
                ),
                required_resolution="resolve_action",
                can_be_overridden_by_approval=True,
                metadata=_with_action_history(
                    {
                        "target_node_id": run.target_node_id,
                        "judge_result": run.judge_result,
                        "status": run.status,
                        "review_required": bool(needs_review and not failed),
                    },
                    ctx=ctx,
                    stage=3,
                    source_type="eval_run",
                    source_id=run.run_id,
                    pending_action_id=_find_pending_action_id(
                        ctx, 3, source_type="eval_run", source_id=run.run_id
                    ),
                ),
            )
        )
    return blockers


def _collect_stage4_final_blockers(ctx: ProjectContext) -> list[StageBlocker]:
    """Final governance gate aligned with upstream stage blockers.

    Stage 4 completion must not contradict report/export governance. It wraps
    unresolved upstream hard blockers into final_governance blockers while
    preserving the original source and required_resolution so the resolution
    operation remains accurate.
    """
    blockers: list[StageBlocker] = []

    for upstream_stage in range(1, 4):
        upstream = evaluate_stage_gate(ctx, upstream_stage)
        for blocker in upstream.blockers:
            if blocker.blocker_type == "missing_stage_output" and not is_stage_actionable(
                ctx, upstream_stage
            ):
                continue
            if blocker.can_be_overridden_by_approval:
                # Overridable items stay visible in their native stage. Final
                # governance only hard-blocks what cannot be approval-overridden.
                continue
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="final_governance",
                    severity=blocker.severity,
                    message=f"流程完成前上游阶段{upstream_stage}仍有未关闭治理项：{blocker.message}",
                    source_type=blocker.source_type,
                    source_id=blocker.source_id or blocker.blocker_id,
                    action_id=blocker.action_id,
                    required_resolution=blocker.required_resolution,
                    can_be_overridden_by_approval=False,
                    metadata={
                        "upstream_stage_id": upstream_stage,
                        "upstream_blocker_id": blocker.blocker_id,
                        "upstream_blocker_type": blocker.blocker_type,
                        "upstream_required_resolution": blocker.required_resolution,
                        "upstream_metadata": blocker.metadata,
                    },
                )
            )

    for finding in ctx.safety_findings:
        if finding.status == "open" and finding.severity in {"high", "critical"}:
            action_id = None
            if finding.stage_id is not None:
                action_id = _find_pending_action_id(
                    ctx,
                    finding.stage_id,
                    source_type="safety_finding",
                    source_id=finding.finding_id,
                )
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="final_governance",
                    severity=finding.severity,
                    message=f"流程完成前仍有 {finding.severity} 安全发现未关闭：{finding.finding_id}。",
                    source_type="safety_finding",
                    source_id=finding.finding_id,
                    action_id=action_id,
                    required_resolution="resolve_action" if action_id else "resolve_safety_finding",
                    can_be_overridden_by_approval=finding.severity != "critical",
                    metadata={"risk_type": finding.risk_type, "stage_id": finding.stage_id},
                )
            )

    for key, value in ctx.parser_errors.items():
        if key.startswith("stage_") and value:
            stage_token = key.split("_", 1)[-1]
            source_stage = int(stage_token) if stage_token.isdigit() else 4
            action_id = _find_pending_action_id(
                ctx, source_stage, source_type="parser", source_id=key
            )
            blockers.append(
                _blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="final_governance",
                    severity="high",
                    message=f"流程完成前仍有 parser error 未关闭：{key}。",
                    source_type="parser",
                    source_id=key,
                    action_id=action_id,
                    required_resolution="edit_stage_output",
                    can_be_overridden_by_approval=False,
                    metadata={
                        "parser_error": value,
                        "requires_structured_output": True,
                        "expected_schema": f"Stage{source_stage}Schema",
                    },
                )
            )
    return blockers


def evaluate_stage_gate(ctx: ProjectContext, stage: int) -> StageGateResult:
    """Evaluate the authoritative stage gate without mutating state.

    v0.7 delegates rule collection to core.gates.engine while preserving the
    public StageGateResult contract used by API/frontend/report code.
    """
    from core.gates.engine import evaluate_stage_gate as evaluate_with_gate_engine

    return evaluate_with_gate_engine(ctx, stage)


def stage_can_continue(ctx: ProjectContext, stage: int) -> tuple[bool, str]:
    """Backward-compatible tuple contract used by graph.nodes."""
    result = evaluate_stage_gate(ctx, stage)
    if result.can_continue:
        return True, ""
    return False, result.blockers[0].message if result.blockers else "阶段暂不能继续推进。"


def assert_stage_can_advance(ctx: ProjectContext, stage: int) -> StageGateResult:
    """Return the authoritative gate result for callers that need a single source of truth.

    The function is intentionally non-mutating. Callers decide whether to raise,
    show blockers, or route to stage_resolution_service for concrete operations.
    """
    return evaluate_stage_gate(ctx, stage)


def get_stage_gate_result(ctx: ProjectContext, stage: int) -> dict[str, Any]:
    """API/report-friendly gate result for one stage."""
    return assert_stage_can_advance(ctx, stage).model_dump(mode="json")


def _operation_text(required_resolution: str) -> str:
    mapping = {
        "run_stage": "先运行当前阶段，生成结构化输出。",
        "rerun_stage": "上游输出已更新，请重跑该阶段以刷新依赖版本。",
        "resolve_action": "处理对应 PendingHumanAction。",
        "verify_evidence": "核验证据；dismiss 只关闭动作，不解除高风险证据门控。",
        "edit_stage_output": "通过 edit action 或 revise 当前阶段修正结构化输出。",
        "revise_stage": "修改或回退当前阶段，生成新的 stage_output_version。",
        "back_stage": "回退到上一阶段并废弃当前阻断动作。",
        "approve_escalation": "升级风险必须由负责人明确 approve。",
        "resolve_safety_finding": "关闭或批准对应 SafetyFinding，并保留审计记录。",
        "run_eval_experiment": "运行或重新创建并运行对应 EvalExperiment，完成后再评估回归门禁。",
        "compare_eval_experiment": "将当前 EvalExperiment 与 baseline 生成 comparison_summary。",
    }
    return mapping.get(required_resolution, required_resolution)


def build_stage_readiness(ctx: ProjectContext) -> dict[str, dict[str, Any]]:
    """Build stage readiness for API/frontend/report from the same gate result.

    v0.6.0-alpha.8 keeps future not-started stages visible as placeholders but
    removes their missing_stage_output blockers from current advancement and
    report governance queues.
    """
    readiness: dict[str, dict[str, Any]] = {}
    actionables = set(actionable_stage_ids(ctx))
    active_stage = current_stage_id(ctx)
    for stage in range(1, 5):
        actionable = stage in actionables
        version = _current_version(ctx, stage)
        key = f"stage_{stage}"
        dependency_versions = dict(getattr(ctx, "stage_dependency_versions", {}).get(key, {}) or {})
        stale_meta = dict(getattr(ctx, "stage_staleness", {}).get(key, {}) or {})
        pending_actions = [
            action
            for action in ctx.pending_actions
            if action.stage_id == stage
            and action.stage_output_version == version
            and action.status == HumanActionStatus.PENDING.value
        ]
        open_safety = [
            finding
            for finding in ctx.safety_findings
            if finding.stage_id == stage and finding.status == "open"
        ]

        if actionable:
            result = evaluate_stage_gate(ctx, stage)
            lifecycle = _stage_lifecycle(ctx, stage, result)
            blockers = result.blockers
            can_continue = result.can_continue
            block_reason = (
                ""
                if result.can_continue
                else (result.blockers[0].message if result.blockers else "")
            )
        else:
            result = StageGateResult(
                stage_id=stage, stage_output_version=version, can_continue=False, blockers=[]
            )
            lifecycle = "not_started"
            blockers = []
            can_continue = False
            block_reason = ""

        operations: list[str] = []
        for blocker in blockers:
            op = _operation_text(blocker.required_resolution)
            if op not in operations:
                operations.append(op)

        stage_metadata: dict[str, Any] = {
            "current_stage_id": active_stage,
            "is_actionable": actionable,
        }
        if not actionable:
            stage_metadata["visibility_reason"] = "future_stage_not_reached"
        if stage == 2:
            stage_metadata["stage_2_coverage_matrix"] = _stage_2_coverage_matrix(ctx)
        if stage == 3:
            from core.eval_regression_policy import build_stage_eval_regression_summary
            from core.trace_backfill_service import build_trace_backfill_summary

            stage_metadata["stage_3_coverage_warning"] = _stage_3_coverage_warning(ctx)
            stage_metadata["stage_3_eval_regression_summary"] = build_stage_eval_regression_summary(
                ctx, stage=3
            )
            stage_metadata["stage_3_trace_backfill_summary"] = build_trace_backfill_summary(ctx)
        if stage == 4:
            stage_metadata["final_governance_summary"] = _build_final_governance_summary(ctx)

        item = StageReadiness(
            stage_id=stage,
            state=getattr(ctx.current_state, "value", str(ctx.current_state)),
            stage_output_exists=_stage_output_exists(ctx, stage),
            stage_output_version=version,
            stage_lifecycle=lifecycle,
            can_continue=can_continue,
            block_reason=block_reason,
            blockers=blockers,
            pending_action_ids=[action.action_id for action in pending_actions],
            pending_blocking_action_ids=[
                action.action_id for action in pending_actions if action.blocking
            ],
            open_safety_finding_ids=[finding.finding_id for finding in open_safety],
            parser_error=ctx.parser_errors.get(f"stage_{stage}", ""),
            recommended_next_operations=operations,
            stage_dependency_versions=dependency_versions,
            stale_reason=str(stale_meta.get("reason", "")),
            stage_metadata=stage_metadata,
            is_actionable=actionable,
            future_stage=not actionable,
            visibility_reason="" if actionable else "future_stage_not_reached",
        )
        readiness[f"stage_{stage}"] = item.model_dump(mode="json")
    return readiness


def get_stage_readiness(ctx: ProjectContext, stage: int) -> dict[str, Any]:
    key = f"stage_{stage}"
    readiness = build_stage_readiness(ctx)
    if key not in readiness:
        raise ValueError(f"stage must be 1..4, got {stage}")
    return readiness[key]


def _build_final_governance_summary(ctx: ProjectContext) -> dict[str, Any]:
    high_safety = [
        finding.finding_id
        for finding in ctx.safety_findings
        if finding.status == "open" and finding.severity == "high"
    ]
    critical_safety = [
        finding.finding_id
        for finding in ctx.safety_findings
        if finding.status == "open" and finding.severity == "critical"
    ]
    pending_blocking_actions = [
        action.action_id
        for action in ctx.pending_actions
        if action.status == HumanActionStatus.PENDING.value and action.blocking
    ]
    parser_error_keys = [
        key for key, value in ctx.parser_errors.items() if key.startswith("stage_") and value
    ]
    failed_high_risk_eval_ids = [
        blocker.source_id for blocker in _collect_stage3_eval_blockers(ctx) if blocker.source_id
    ]
    stage3_gate_blockers = evaluate_stage_gate(ctx, 3).blockers
    eval_regression_blockers = [
        blocker.model_dump(mode="json")
        for blocker in stage3_gate_blockers
        if blocker.blocker_type == "eval_regression"
    ]
    trace_backfill_blockers = [
        blocker.model_dump(mode="json")
        for blocker in stage3_gate_blockers
        if blocker.blocker_type == "trace_backfill_gap"
    ]
    unverified_high_risk_evidence = _unverified_high_risk_evidence(ctx)
    stale_stage_outputs = [
        key
        for key, value in getattr(ctx, "stage_staleness", {}).items()
        if isinstance(value, dict) and value.get("stale")
    ]
    return {
        "open_high_safety_findings": high_safety,
        "open_critical_safety_findings": critical_safety,
        "pending_blocking_action_ids": pending_blocking_actions,
        "parser_error_keys": parser_error_keys,
        "failed_high_risk_eval_ids": failed_high_risk_eval_ids,
        "eval_regression_blockers": eval_regression_blockers,
        "trace_backfill_blockers": trace_backfill_blockers,
        "unverified_high_risk_evidence": unverified_high_risk_evidence,
        "stale_stage_outputs": stale_stage_outputs,
        "report_export_allowed": not (
            pending_blocking_actions
            or high_safety
            or critical_safety
            or parser_error_keys
            or failed_high_risk_eval_ids
            or eval_regression_blockers
            or trace_backfill_blockers
            or unverified_high_risk_evidence
            or stale_stage_outputs
        ),
    }


def _unverified_high_risk_evidence(ctx: ProjectContext) -> list[dict[str, Any]]:
    evidence_by_id = {ev.evidence_id: ev for ev in ctx.evidence_sources}
    items: list[dict[str, Any]] = []
    if ctx.stage_1_output:
        for fm in ctx.stage_1_output.failure_modes:
            if str(fm.severity).lower() not in {"high", "critical"}:
                continue
            for evidence_id in getattr(fm, "evidence_ids", []) or []:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None or evidence.verified:
                    continue
                items.append(
                    {
                        "failure_mode_id": fm.id,
                        "evidence_id": evidence_id,
                        "source_type": evidence.source_type,
                        "credibility_score": evidence.credibility_score,
                    }
                )
    return items


def build_unresolved_governance_items(ctx: ProjectContext) -> dict[str, Any]:
    """Unified unresolved governance summary.

    Keeps legacy report keys while adding structured stage_blockers so old report
    readers continue to work and new UI/API consumers get precise operations.
    """
    readiness = build_stage_readiness(ctx)
    blockers = [
        blocker for stage_item in readiness.values() for blocker in stage_item.get("blockers", [])
    ]
    failed_eval_items = []
    for case in ctx.eval_cases:
        if case.passed is False:
            failed_eval_items.append(
                {
                    "type": "eval_case",
                    "id": case.eval_id,
                    "target_node_id": case.target_node_id,
                    "scenario_type": case.scenario_type,
                }
            )
    for run in ctx.eval_runs:
        if run.status == "failed" or run.judge_result in {"failed", "needs_review"}:
            failed_eval_items.append(
                {
                    "type": "eval_run",
                    "id": run.run_id,
                    "target_node_id": run.target_node_id,
                    "judge_result": run.judge_result,
                }
            )

    eval_regression_blockers = [
        blocker for blocker in blockers if blocker.get("blocker_type") == "eval_regression"
    ]
    trace_backfill_blockers = [
        blocker for blocker in blockers if blocker.get("blocker_type") == "trace_backfill_gap"
    ]

    recommended_next_operations: list[str] = []
    for stage_item in readiness.values():
        for operation in stage_item.get("recommended_next_operations", []):
            if operation not in recommended_next_operations:
                recommended_next_operations.append(operation)

    return {
        "pending_actions": [
            _dump(action)
            for action in ctx.pending_actions
            if action.status == HumanActionStatus.PENDING.value
        ],
        "open_high_critical_safety_findings": [
            _dump(finding)
            for finding in ctx.safety_findings
            if finding.status == "open" and finding.severity in {"high", "critical"}
        ],
        "parser_errors": dict(ctx.parser_errors),
        "unverified_high_risk_evidence": _unverified_high_risk_evidence(ctx),
        "failed_eval_items": failed_eval_items,
        "eval_regression_blockers": eval_regression_blockers,
        "trace_backfill_blockers": trace_backfill_blockers,
        "stage_blockers": blockers,
        "recommended_next_operations": recommended_next_operations,
    }
