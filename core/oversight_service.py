# core/oversight_service.py
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from core.audit_service import append_audit_event
from core.evidence_service import extract_evidence_ids
from core.models import (
    ActionResolutionLog,
    ActionResolutionResult,
    FlagStatus,
    HumanActionStatus,
    PendingHumanAction,
    ProjectContext,
)
from graph.transition_policy import assert_action_resolution_allowed

EVIDENCE_POLICY: dict[str, dict[str, Any]] = {
    "critical": {"min_evidence_count": 1, "min_credibility_score": 0.6, "blocking": True},
    "high": {"min_evidence_count": 1, "min_credibility_score": 0.5, "blocking": True},
    "medium": {"min_evidence_count": 0, "min_credibility_score": 0.4, "blocking": False},
    "low": {"min_evidence_count": 0, "min_credibility_score": 0.0, "blocking": False},
}


def _model_payload(value: Any) -> dict:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"value": value}


def _stable_hash(value: Any) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _action_resolution_log_exists(
    ctx: ProjectContext, action_id: str, idempotency_key: str | None
) -> bool:
    if not idempotency_key:
        return False
    return any(
        log.action_id == action_id
        and log.idempotency_key == idempotency_key
        and log.result_status in {"resolved", "idempotent_replay"}
        for log in getattr(ctx, "action_resolution_logs", []) or []
    )


def _append_action_resolution_log(
    ctx: ProjectContext,
    *,
    action_id: str,
    idempotency_key: str | None,
    requested_status: str,
    result_status: str,
    before_hash: str | None = None,
    after_hash: str | None = None,
    error_message: str | None = None,
) -> ActionResolutionLog:
    log = ActionResolutionLog(
        session_id=ctx.session_id,
        action_id=action_id,
        idempotency_key=idempotency_key,
        requested_status=requested_status,
        result_status=result_status,
        before_hash=before_hash,
        after_hash=after_hash,
        error_message=error_message,
    )
    ctx.action_resolution_logs.append(log)
    return log


def _latest_action_resolution_log(
    ctx: ProjectContext, action_id: str, idempotency_key: str | None = None
) -> ActionResolutionLog | None:
    logs = [
        log
        for log in getattr(ctx, "action_resolution_logs", []) or []
        if log.action_id == action_id
        and (idempotency_key is None or log.idempotency_key == idempotency_key)
    ]
    if not logs:
        return None
    return sorted(logs, key=lambda item: item.created_at)[-1]


def _target_object_exists(ctx: ProjectContext, action: PendingHumanAction) -> bool:
    """Best-effort target_object_path guard for action contracts.

    The project still supports legacy actions. Missing target paths are accepted,
    but known target paths must resolve to an existing stage object or to a
    valid stage-level parser/evidence-gap target.
    """

    if not action.target_object_path:
        return True

    source_type = action.source_type or ""
    source_id = action.source_id
    stage = action.stage_id

    if source_type in {"", "unknown"}:
        return True

    if source_type == "parser":
        return source_id in {None, f"stage_{stage}"} or f"stage_{stage}" in ctx.parser_errors

    if source_type == "flag":
        return any(flag.item_id == source_id for flag in ctx.flagged_items)

    if source_type == "failure_mode":
        return bool(
            ctx.stage_1_output
            and any(item.id == source_id for item in ctx.stage_1_output.failure_modes)
        )

    if source_type in {
        "evidence_gap",
        "evidence_low_credibility",
        "evidence_unverified_for_high_risk",
    }:
        return True

    if source_type in {"workflow_policy", "workflow_node"}:
        return bool(
            ctx.stage_2_output
            and any(node.node_id == source_id for node in ctx.stage_2_output.workflow_nodes)
        )

    if source_type in {"stage3_result", "stress_test"}:
        return ctx.stage_3_output is not None

    if source_type == "eval_run":
        return any(run.run_id == source_id for run in ctx.eval_runs)

    if source_type == "trigger_method":
        return bool(
            ctx.stage_4_output
            and any(method.node_id == source_id for method in ctx.stage_4_output.trigger_methods)
        )

    if source_type == "safety_finding":
        return any(finding.finding_id == source_id for finding in ctx.safety_findings)

    return True


def current_stage_output_version(ctx: ProjectContext, stage: int) -> int:
    return int(ctx.stage_output_versions.get(f"stage_{stage}", 1))


def bump_stage_output_version(ctx: ProjectContext, stage: int) -> int:
    key = f"stage_{stage}"
    version = int(ctx.stage_output_versions.get(key, 0)) + 1
    ctx.stage_output_versions[key] = version
    return version


def _has_action(
    ctx: ProjectContext,
    *,
    stage_id: int,
    source_type: str,
    source_id: str | None,
    action_type: str,
    stage_output_version: int,
    include_inactive: bool = False,
) -> bool:
    inactive = {HumanActionStatus.CANCELLED.value, HumanActionStatus.SUPERSEDED.value}
    for action in ctx.pending_actions:
        if (
            action.stage_id == stage_id
            and action.source_type == source_type
            and action.source_id == source_id
            and action.action_type == action_type
            and action.stage_output_version == stage_output_version
        ):
            if include_inactive or action.status not in inactive:
                return True
    return False


def add_action_if_missing(
    ctx: ProjectContext,
    *,
    stage_id: int,
    action_type: str,
    title: str,
    description: str,
    risk_level: str = "medium",
    trigger_reason: str = "",
    source_type: str = "",
    source_id: str | None = None,
    node_id: str | None = None,
    payload_before: dict | None = None,
    blocking: bool = True,
    stage_output_version: int | None = None,
) -> PendingHumanAction | None:
    """幂等创建人工动作；幂等范围绑定到当前阶段输出版本。"""
    version = stage_output_version or current_stage_output_version(ctx, stage_id)
    if _has_action(
        ctx,
        stage_id=stage_id,
        source_type=source_type,
        source_id=source_id,
        action_type=action_type,
        stage_output_version=version,
    ):
        return None

    action = PendingHumanAction(
        session_id=ctx.session_id,
        stage_id=stage_id,
        node_id=node_id,
        source_type=source_type,
        source_id=source_id,
        action_type=action_type,
        title=title,
        description=description,
        risk_level=risk_level,  # type: ignore[arg-type]
        trigger_reason=trigger_reason,
        payload_before=payload_before or {},
        blocking=blocking,
        stage_output_version=version,
        target_stage=stage_id,
        target_stage_version=version,
        target_object_path=f"stage_{stage_id}.{source_type or 'unknown'}.{source_id or 'stage'}",
        expected_before_hash=_stable_hash(payload_before or {}),
    )
    ctx.pending_actions.append(action)
    append_audit_event(
        ctx,
        actor="system",
        event_type="human_action_created",
        target_type="human_action",
        target_id=action.action_id,
        after=action,
        metadata={
            "stage_id": stage_id,
            "stage_output_version": version,
            "source_type": source_type,
            "source_id": source_id,
            "action_type": action_type,
        },
    )
    return action


def create_actions_from_flags(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """把【需核验】低层信号升级为正式 verify_evidence 动作。"""
    created: list[PendingHumanAction] = []
    for flag in ctx.flagged_items:
        if flag.stage != stage or flag.status != FlagStatus.PENDING:
            continue
        action = add_action_if_missing(
            ctx,
            stage_id=stage,
            source_type="flag",
            source_id=flag.item_id,
            action_type="verify_evidence",
            title=f"核验阶段{stage}的不确定内容",
            description=flag.content,
            risk_level="medium",
            trigger_reason="AI 输出中包含【需核验】标记",
            payload_before=_model_payload(flag),
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_failure_modes(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """阶段一 high/critical 失败模式需要人工处理后才能继续。"""
    if stage != 1 or not ctx.stage_1_output:
        return []

    created: list[PendingHumanAction] = []
    for fm in ctx.stage_1_output.failure_modes:
        severity = str(fm.severity).lower()
        if severity not in {"high", "critical"}:
            continue
        action_type = "escalate" if severity == "critical" else "approve"
        action = add_action_if_missing(
            ctx,
            stage_id=1,
            source_type="failure_mode",
            source_id=fm.id,
            action_type=action_type,
            title=f"确认高风险失败模式：{fm.id}",
            description=f"{fm.category}：{fm.description}",
            risk_level=severity,
            trigger_reason=f"阶段一识别到 {severity} 风险失败模式",
            payload_before=_model_payload(fm),
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_evidence_gaps(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Create severity-aware evidence review actions.

    high/critical failure modes must have enough evidence, must not rely only on
    weak sources, and must be manually verified before automatic continuation.
    """
    if stage != 1 or not ctx.stage_1_output:
        return []

    evidence_by_id = {ev.evidence_id: ev for ev in ctx.evidence_sources}
    created: list[PendingHumanAction] = []
    for fm in ctx.stage_1_output.failure_modes:
        severity = str(fm.severity).lower()
        policy = EVIDENCE_POLICY.get(severity, EVIDENCE_POLICY["medium"])
        evidence_ids = list(
            dict.fromkeys(
                (getattr(fm, "evidence_ids", []) or []) + extract_evidence_ids(fm.evidence)
            )
        )
        min_count = int(policy["min_evidence_count"])
        min_score = float(policy["min_credibility_score"])
        blocking = bool(policy["blocking"])

        if len(evidence_ids) < min_count:
            action = add_action_if_missing(
                ctx,
                stage_id=1,
                source_type="evidence_gap",
                source_id=fm.id,
                action_type="edit",
                title=f"补充失败模式证据引用：{fm.id}",
                description=f"{fm.category}：{fm.description}",
                risk_level=severity,
                trigger_reason="失败模式没有满足 evidence_id 数量要求，必须编辑 Stage1 structured_output 补充 evidence_ids",
                payload_before={
                    "failure_mode": _model_payload(fm),
                    "required_min_evidence_count": min_count,
                    "found_evidence_ids": evidence_ids,
                    "requires_structured_output": True,
                    "expected_schema": "Stage1Schema",
                },
                blocking=blocking,
                stage_output_version=stage_output_version,
            )
            if action:
                created.append(action)
            continue

        weak_sources = [
            ev
            for ev_id in evidence_ids
            if (ev := evidence_by_id.get(ev_id)) is not None
            and (ev.credibility_score < min_score or ev.source_type in {"unknown", "forum"})
        ]
        if weak_sources and severity in {"medium", "high", "critical"}:
            action = add_action_if_missing(
                ctx,
                stage_id=1,
                source_type="evidence_low_credibility",
                source_id=fm.id,
                action_type="verify_evidence",
                title=f"核验低可信证据：{fm.id}",
                description=f"失败模式 {fm.id} 引用了低可信、论坛或未知来源证据。",
                risk_level=severity,
                trigger_reason="风险结论依赖低可信/未知来源",
                payload_before={
                    "failure_mode": _model_payload(fm),
                    "required_min_credibility_score": min_score,
                    "weak_sources": [_model_payload(ev) for ev in weak_sources],
                },
                blocking=blocking,
                stage_output_version=stage_output_version,
            )
            if action:
                created.append(action)

        unverified_sources = [
            ev
            for ev_id in evidence_ids
            if (ev := evidence_by_id.get(ev_id)) is not None and not ev.verified
        ]
        if unverified_sources and severity in {"high", "critical"}:
            action = add_action_if_missing(
                ctx,
                stage_id=1,
                source_type="evidence_unverified_for_high_risk",
                source_id=fm.id,
                action_type="verify_evidence",
                title=f"人工核验高风险证据：{fm.id}",
                description=f"高风险失败模式 {fm.id} 的证据尚未人工核验。",
                risk_level=severity,
                trigger_reason="high/critical 失败模式引用的证据未人工核验",
                payload_before={
                    "failure_mode": _model_payload(fm),
                    "unverified_sources": [_model_payload(ev) for ev in unverified_sources],
                },
                blocking=True,
                stage_output_version=stage_output_version,
            )
            if action:
                created.append(action)
    return created


def create_actions_from_workflow_policies(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """根据 Stage 2 WorkflowNode.oversight_policy 创建正式人工动作。"""
    if stage != 2 or not ctx.stage_2_output:
        return []

    created: list[PendingHumanAction] = []
    for node in ctx.stage_2_output.workflow_nodes:
        policy = node.oversight_policy
        if policy is None:
            continue
        if policy.can_auto_continue and policy.risk_level not in {"high", "critical"}:
            continue

        required_action = policy.required_action
        if policy.risk_level == "critical":
            required_action = "escalate"
        action = add_action_if_missing(
            ctx,
            stage_id=2,
            source_type="oversight_policy",
            source_id=policy.policy_id,
            node_id=node.node_id,
            action_type=required_action,
            title=f"处理节点 {node.node_id} 的人工监督策略",
            description=policy.trigger_reason,
            risk_level=policy.risk_level,
            trigger_reason=policy.trigger_reason,
            payload_before={
                "node": _model_payload(node),
                "policy": _model_payload(policy),
            },
            blocking=not policy.can_auto_continue,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_stage3_result(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """阶段三整体未通过时，要求人工编辑或回退工作流。"""
    if stage != 3 or not ctx.stage_3_output:
        return []
    if ctx.stage_3_output.overall_passed:
        return []

    action = add_action_if_missing(
        ctx,
        stage_id=3,
        source_type="stress_test",
        source_id="stage_3_overall",
        action_type="edit",
        title="处理阶段三压测未通过结果",
        description="阶段三整体压测未通过，需要人工决定修改压测输入、回退工作流设计或带风险继续。",
        risk_level="high",
        trigger_reason="Stage3Output.overall_passed=False",
        payload_before=_model_payload(ctx.stage_3_output),
        blocking=True,
        stage_output_version=stage_output_version,
    )
    return [action] if action else []


def _risk_for_failure_mode_ids(ctx: ProjectContext, failure_mode_ids: list[str]) -> str:
    severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    highest = "medium"
    if not ctx.stage_1_output:
        return highest
    severity_by_id = {fm.id: str(fm.severity).lower() for fm in ctx.stage_1_output.failure_modes}
    for failure_mode_id in failure_mode_ids:
        severity = severity_by_id.get(failure_mode_id, "medium")
        if severity_order.get(severity, 1) > severity_order.get(highest, 1):
            highest = severity
    return highest


def _high_risk_node_ids_for_eval(ctx: ProjectContext) -> set[str]:
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


def create_actions_from_eval_failures(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Create review actions when Stage 3 eval gates need human closure."""
    if stage != 3:
        return []

    created: list[PendingHumanAction] = []
    high_risk_nodes = _high_risk_node_ids_for_eval(ctx)
    covered_nodes = {case.target_node_id for case in ctx.eval_cases if case.target_node_id}

    for node_id in sorted(high_risk_nodes - covered_nodes):
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="eval_coverage",
            source_id=node_id,
            action_type="edit",
            title=f"补充高风险节点 EvalCase 覆盖：{node_id}",
            description="Stage 3 must include at least one EvalCase for each high-risk workflow node before advancement.",
            risk_level="high",
            trigger_reason="High-risk workflow node lacks Stage 3 EvalCase coverage.",
            node_id=node_id,
            payload_before={
                "target_node_id": node_id,
                "missing_eval_coverage": True,
                "requires_structured_output": True,
                "expected_schema": "Stage3Schema",
            },
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    for case in ctx.eval_cases:
        if case.passed is not False:
            continue
        risk_level = _risk_for_failure_mode_ids(ctx, case.covered_failure_mode_ids or [])
        action_type = (
            "escalate"
            if risk_level == "critical"
            else "edit"
            if risk_level == "high"
            else "approve"
        )
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="eval_case",
            source_id=case.eval_id,
            action_type=action_type,
            title=f"Resolve failed eval case: {case.eval_id}",
            description=f"EvalCase failed for node {case.target_node_id or 'unknown'}.",
            risk_level=risk_level,
            trigger_reason="EvalCase.passed=False",
            node_id=case.target_node_id,
            payload_before=_model_payload(case),
            blocking=risk_level in {"high", "critical"},
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    for run in ctx.eval_runs:
        failed = run.judge_result == "failed" or run.status == "failed"
        needs_review = run.judge_result == "needs_review"
        if not (failed or needs_review):
            continue
        risk_level = _risk_for_failure_mode_ids(ctx, run.covered_failure_mode_ids or [])
        is_high_risk_path = (
            risk_level in {"high", "critical"} or run.target_node_id in high_risk_nodes
        )
        if needs_review and not is_high_risk_path:
            continue
        action_type = (
            "escalate"
            if risk_level == "critical"
            else "edit"
            if risk_level == "high"
            else "approve"
        )
        title_prefix = (
            "Review required eval run" if needs_review and not failed else "Resolve failed eval run"
        )
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="eval_run",
            source_id=run.run_id,
            action_type=action_type,
            title=f"{title_prefix}: {run.run_id}",
            description=(
                f"EvalRun for eval {run.eval_id} on node {run.target_node_id or 'unknown'} "
                f"returned judge_result={run.judge_result} status={run.status}."
            ),
            risk_level="high"
            if needs_review and risk_level not in {"high", "critical"}
            else risk_level,
            trigger_reason=run.judge_reason or run.error_message or "EvalRun requires human review",
            node_id=run.target_node_id,
            payload_before=_model_payload(run),
            blocking=is_high_risk_path,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    return created


def create_actions_from_trigger_methods(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Stage 4 trigger method 若声明需要人工审核，则创建 approve 动作。"""
    if stage != 4 or not ctx.stage_4_output:
        return []

    created: list[PendingHumanAction] = []
    for method in ctx.stage_4_output.trigger_methods:
        if not getattr(method, "human_review_required", False):
            continue
        action = add_action_if_missing(
            ctx,
            stage_id=4,
            source_type="trigger_method",
            source_id=method.node_id,
            node_id=method.node_id,
            action_type="approve",
            title=f"确认触发方式需要人工审核：{method.node_id}",
            description=method.execution_suggestion or method.trigger_instruction,
            risk_level="high",
            trigger_reason="TriggerMethod.human_review_required=True",
            payload_before=_model_payload(method),
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_safety_findings(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """high/critical safety finding 会阻断自动推进。"""
    created: list[PendingHumanAction] = []
    for finding in ctx.safety_findings:
        if finding.stage_id != stage or finding.status != "open":
            continue
        if finding.severity not in {"high", "critical"} or not finding.requires_human_review:
            continue
        action_type = "escalate" if finding.severity == "critical" else "approve"
        action = add_action_if_missing(
            ctx,
            stage_id=stage,
            source_type="safety_finding",
            source_id=finding.finding_id,
            action_type=action_type,
            title=f"处理安全发现：{finding.risk_type}",
            description=finding.description,
            risk_level=finding.severity,
            trigger_reason=finding.recommended_action,
            payload_before=_model_payload(finding),
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_parser_errors(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """结构化解析失败时，创建人工编辑动作。"""
    error = ctx.parser_errors.get(f"stage_{stage}")
    if not error:
        return []

    output = getattr(ctx, f"stage_{stage}_output", None)
    action = add_action_if_missing(
        ctx,
        stage_id=stage,
        source_type="parser",
        source_id=f"stage_{stage}",
        action_type="edit",
        title=f"修复阶段{stage}结构化解析失败",
        description="AI 输出无法稳定解析为目标结构，需要人工编辑或要求模型重跑。",
        risk_level="high",
        trigger_reason=error,
        payload_before={
            "stage_output": _model_payload(output),
            "parser_error": error,
            "requires_structured_output": True,
            "expected_schema": f"Stage{stage}Schema",
        },
        blocking=True,
        stage_output_version=stage_output_version,
    )
    return [action] if action else []


def create_review_actions_for_stage(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """统一入口：根据阶段输出创建所有必要人工动作。"""
    created: list[PendingHumanAction] = []
    created.extend(create_actions_from_flags(ctx, stage, stage_output_version=stage_output_version))
    created.extend(
        create_actions_from_failure_modes(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_evidence_gaps(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_workflow_policies(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_stage3_result(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_eval_failures(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_trigger_methods(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_safety_findings(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_parser_errors(ctx, stage, stage_output_version=stage_output_version)
    )
    return created


def resolve_action(
    ctx: ProjectContext,
    *,
    action_id: str,
    decision: str,
    note: str = "",
    payload_after: dict | None = None,
    idempotency_key: str | None = None,
    expected_before_hash: str | None = None,
) -> PendingHumanAction:
    """处理人工动作，并同步底层 FlaggedItem / reviewed_outputs / 审计记录。

    Applies a conservative idempotency contract around stage advancement semantics.
    Edit payloads are validated before status transition, and duplicate submissions
    with the same idempotency key replay the already-resolved action without creating
    duplicate audit events.
    """
    for action in ctx.pending_actions:
        if action.action_id != action_id:
            continue

        before = action.model_dump(mode="json")
        before_hash = _stable_hash(before)
        before_payload_hash = _stable_hash(action.payload_before or {})
        effective_idempotency_key = idempotency_key or action.idempotency_key

        if action.status != HumanActionStatus.PENDING.value:
            if _action_resolution_log_exists(ctx, action_id, effective_idempotency_key):
                return action
            raise ValueError(f"Action is not pending: {action_id}")

        action.resolution_attempts += 1
        current_version = current_stage_output_version(ctx, action.stage_id)
        if action.stage_output_version != current_version:
            action.last_resolution_error = f"stale action version {action.stage_output_version}; current stage version is {current_version}"
            _append_action_resolution_log(
                ctx,
                action_id=action.action_id,
                idempotency_key=effective_idempotency_key,
                requested_status=decision,
                result_status="stale",
                before_hash=before_hash,
                error_message=action.last_resolution_error,
            )
            raise ValueError(action.last_resolution_error)

        if expected_before_hash and expected_before_hash not in {before_hash, before_payload_hash}:
            action.last_resolution_error = (
                "expected_before_hash does not match current action payload"
            )
            _append_action_resolution_log(
                ctx,
                action_id=action.action_id,
                idempotency_key=effective_idempotency_key,
                requested_status=decision,
                result_status="conflict",
                before_hash=before_hash,
                error_message=action.last_resolution_error,
            )
            raise ValueError(action.last_resolution_error)

        try:
            effect = assert_action_resolution_allowed(action, decision, payload_after=payload_after)

            # ── edit: apply structured output BEFORE marking resolved ──
            apply_result = None
            reviewed_key: str | None = None
            before_reviewed = None
            if action.action_type == "edit" and decision == "edit" and payload_after:
                from core.reviewed_output_service import apply_reviewed_output_with_result

                reviewed_key = f"stage_{action.stage_id}"
                before_reviewed = ctx.reviewed_outputs.get(reviewed_key)
                apply_result = apply_reviewed_output_with_result(
                    ctx, action.stage_id, payload_after
                )

            # ── safe: mark action resolved ──
            action.status = HumanActionStatus.RESOLVED.value
            action.reviewer_decision = decision
            action.reviewer_note = note or effect.message
            action.payload_after = payload_after
            action.idempotency_key = effective_idempotency_key
            action.target_stage = action.target_stage or action.stage_id
            action.target_stage_version = action.target_stage_version or action.stage_output_version
            action.approved_payload_hash = (
                _stable_hash(payload_after) if payload_after is not None else None
            )
            action.last_resolution_error = None
            action.resolved_at = datetime.utcnow()

            if action.source_type == "flag" and action.source_id:
                for flag in ctx.flagged_items:
                    if flag.item_id == action.source_id:
                        if decision in {"dismiss", "dismissed", "reject"}:
                            flag.status = FlagStatus.DISMISSED
                        else:
                            flag.status = FlagStatus.VERIFIED
                        flag.verified_at = action.resolved_at
                        flag.note = note
                        break

            if action.source_type == "safety_finding" and action.source_id:
                for finding in ctx.safety_findings:
                    if finding.finding_id == action.source_id and decision == "approve":
                        finding.status = "resolved"
                        finding.resolution_note = (
                            note or action.reviewer_note or finding.resolution_note
                        )
                        finding.resolved_at = action.resolved_at
                        break

            if apply_result is not None:
                from tools.safety_classifier import add_findings_dedup, scan_policy_gaps

                if apply_result.applied_to_structured_output:
                    new_version = bump_stage_output_version(ctx, action.stage_id)
                    apply_result.stage_output_version_after = new_version
                    from core.stage_revision_service import (
                        invalidate_downstream_stages,
                        record_stage_dependency_versions,
                    )

                    record_stage_dependency_versions(ctx, action.stage_id)
                    invalidate_downstream_stages(
                        ctx,
                        changed_stage=action.stage_id,
                        reason=f"Stage output edited by action {action.action_id}.",
                        superseded_by=action.action_id,
                    )
                    supersede_actions_for_stage(
                        ctx,
                        stage=action.stage_id,
                        reason=f"Stage output edited by action {action.action_id}; stale actions superseded.",
                        superseded_by=action.action_id,
                    )
                    add_findings_dedup(ctx, scan_policy_gaps(ctx, stage_id=action.stage_id))
                    if action.stage_id == 3:
                        from core.eval_service import sync_eval_cases_from_stage3

                        sync_eval_cases_from_stage3(ctx)
                    create_review_actions_for_stage(
                        ctx, action.stage_id, stage_output_version=new_version
                    )
                append_audit_event(
                    ctx,
                    actor="user",
                    event_type="stage_output_edited",
                    target_type="stage_output",
                    target_id=reviewed_key,
                    before=before_reviewed,
                    after=payload_after,
                    metadata={
                        "action_id": action.action_id,
                        "stage_id": action.stage_id,
                        "stage_output_version_before": apply_result.stage_output_version_before,
                        "stage_output_version_after": apply_result.stage_output_version_after,
                        "applied_to_structured_output": apply_result.applied_to_structured_output,
                        "parser_error_cleared": apply_result.parser_error_cleared,
                        "warnings": apply_result.warnings,
                        "source_type": action.source_type,
                    },
                )

            after_hash = _stable_hash(action)
            _append_action_resolution_log(
                ctx,
                action_id=action.action_id,
                idempotency_key=effective_idempotency_key,
                requested_status=decision,
                result_status="resolved",
                before_hash=before_hash,
                after_hash=after_hash,
            )

            append_audit_event(
                ctx,
                actor="user",
                event_type="human_action_resolved",
                target_type="human_action",
                target_id=action.action_id,
                before=before,
                after=action,
                metadata={
                    "decision": decision,
                    "note": note,
                    "stage_id": action.stage_id,
                    "stage_output_version": action.stage_output_version,
                    "action_type": action.action_type,
                    "allow_continue": effect.allow_continue,
                    "require_revision": effect.require_revision,
                    "require_escalation": effect.require_escalation,
                    "policy_message": effect.message,
                    "idempotency_key": effective_idempotency_key,
                    "expected_before_hash": expected_before_hash,
                    "action_resolution_result": "resolved",
                },
            )
            return action
        except Exception as exc:
            action.last_resolution_error = str(exc)
            _append_action_resolution_log(
                ctx,
                action_id=action.action_id,
                idempotency_key=effective_idempotency_key,
                requested_status=decision,
                result_status="validation_failed" if action.action_type == "edit" else "error",
                before_hash=before_hash,
                error_message=str(exc),
            )
            raise

    raise ValueError(f"Action not found: {action_id}")


def resolve_action_with_result(
    ctx: ProjectContext,
    *,
    action_id: str,
    decision: str,
    note: str = "",
    payload_after: dict | None = None,
    idempotency_key: str | None = None,
    expected_before_hash: str | None = None,
) -> ActionResolutionResult:
    """Resolve an action and return an ActionResolutionResult contract.

    This wrapper preserves the legacy `resolve_action()` behavior for existing
    internal callers while giving API/service callers stable result semantics.
    """

    action = next((item for item in ctx.pending_actions if item.action_id == action_id), None)
    if action is None:
        return ActionResolutionResult(
            session_id=ctx.session_id,
            action_id=action_id,
            requested_status=decision,
            result_status="not_found",
            error_message=f"Action not found: {action_id}",
        )

    before = action.model_dump(mode="json")
    before_hash = _stable_hash(before)
    before_payload_hash = _stable_hash(action.payload_before or {})
    payload_after_hash = _stable_hash(payload_after) if payload_after is not None else None
    effective_idempotency_key = idempotency_key or action.idempotency_key

    replay_log = _latest_action_resolution_log(ctx, action_id, effective_idempotency_key)
    if action.status != HumanActionStatus.PENDING.value:
        if replay_log and replay_log.result_status in {"resolved", "idempotent_replay"}:
            return ActionResolutionResult(
                session_id=ctx.session_id,
                action_id=action_id,
                requested_status=decision,
                result_status="idempotent_replay",
                action_status=action.status,
                before_hash=replay_log.before_hash,
                after_hash=replay_log.after_hash,
                action_hash=replay_log.after_hash,
                payload_before_hash=before_payload_hash,
                payload_after_hash=payload_after_hash,
                log_id=replay_log.log_id,
            )
        return ActionResolutionResult(
            session_id=ctx.session_id,
            action_id=action_id,
            requested_status=decision,
            result_status="not_pending",
            action_status=action.status,
            before_hash=before_hash,
            action_hash=before_hash,
            payload_before_hash=before_payload_hash,
            payload_after_hash=payload_after_hash,
            error_message=f"Action is not pending: {action_id}",
        )

    current_version = current_stage_output_version(ctx, action.stage_id)
    if action.stage_output_version != current_version:
        action.resolution_attempts += 1
        action.status = HumanActionStatus.STALE.value
        action.last_resolution_error = f"stale action version {action.stage_output_version}; current stage version is {current_version}"
        log = _append_action_resolution_log(
            ctx,
            action_id=action.action_id,
            idempotency_key=effective_idempotency_key,
            requested_status=decision,
            result_status="stale",
            before_hash=before_hash,
            error_message=action.last_resolution_error,
        )
        return ActionResolutionResult(
            session_id=ctx.session_id,
            action_id=action.action_id,
            requested_status=decision,
            result_status="stale",
            action_status=action.status,
            before_hash=before_hash,
            action_hash=before_hash,
            payload_before_hash=before_payload_hash,
            payload_after_hash=payload_after_hash,
            log_id=log.log_id,
            error_message=action.last_resolution_error,
        )

    if expected_before_hash and expected_before_hash not in {before_hash, before_payload_hash}:
        action.resolution_attempts += 1
        action.last_resolution_error = "expected_before_hash does not match current action payload"
        log = _append_action_resolution_log(
            ctx,
            action_id=action.action_id,
            idempotency_key=effective_idempotency_key,
            requested_status=decision,
            result_status="conflict",
            before_hash=before_hash,
            error_message=action.last_resolution_error,
        )
        return ActionResolutionResult(
            session_id=ctx.session_id,
            action_id=action.action_id,
            requested_status=decision,
            result_status="conflict",
            action_status=action.status,
            before_hash=before_hash,
            action_hash=before_hash,
            payload_before_hash=before_payload_hash,
            payload_after_hash=payload_after_hash,
            log_id=log.log_id,
            error_message=action.last_resolution_error,
        )

    if not _target_object_exists(ctx, action):
        action.resolution_attempts += 1
        action.last_resolution_error = (
            f"target_object_path does not resolve: {action.target_object_path}"
        )
        log = _append_action_resolution_log(
            ctx,
            action_id=action.action_id,
            idempotency_key=effective_idempotency_key,
            requested_status=decision,
            result_status="conflict",
            before_hash=before_hash,
            error_message=action.last_resolution_error,
        )
        return ActionResolutionResult(
            session_id=ctx.session_id,
            action_id=action.action_id,
            requested_status=decision,
            result_status="conflict",
            action_status=action.status,
            before_hash=before_hash,
            log_id=log.log_id,
            error_message=action.last_resolution_error,
        )

    before_log_count = len(getattr(ctx, "action_resolution_logs", []) or [])
    try:
        resolved = resolve_action(
            ctx,
            action_id=action_id,
            decision=decision,
            note=note,
            payload_after=payload_after,
            idempotency_key=effective_idempotency_key,
            expected_before_hash=expected_before_hash,
        )
    except Exception as exc:  # noqa: BLE001 - convert legacy exception into result contract
        log = _latest_action_resolution_log(ctx, action_id, effective_idempotency_key)
        result_status = "validation_failed" if action.action_type == "edit" else "error"
        if log and log.result_status in {"validation_failed", "conflict", "stale", "error"}:
            result_status = log.result_status  # type: ignore[assignment]
        return ActionResolutionResult(
            session_id=ctx.session_id,
            action_id=action_id,
            requested_status=decision,
            result_status=result_status,  # type: ignore[arg-type]
            action_status=action.status,
            before_hash=before_hash,
            after_hash=log.after_hash if log else None,
            log_id=log.log_id if log else None,
            error_message=str(exc),
        )

    logs = getattr(ctx, "action_resolution_logs", []) or []
    new_logs = logs[before_log_count:]
    log = (
        new_logs[-1]
        if new_logs
        else _latest_action_resolution_log(ctx, action_id, effective_idempotency_key)
    )
    after_hash = _stable_hash(resolved)
    return ActionResolutionResult(
        session_id=ctx.session_id,
        action_id=action_id,
        requested_status=decision,
        result_status="resolved",
        action_status=resolved.status,
        before_hash=before_hash,
        after_hash=after_hash,
        action_hash=after_hash,
        payload_before_hash=before_payload_hash,
        payload_after_hash=payload_after_hash,
        log_id=log.log_id if log else None,
    )


def resolve_actions_for_flag(
    ctx: ProjectContext,
    *,
    flag_id: str,
    decision: str,
    note: str = "",
) -> list[str]:
    """兼容旧 /flags/resolve API：同步处理由 flag 派生的 actions。

    Returns the action_ids resolved by this helper so the session/execution
    coordination layer can apply any execution-mode-specific synchronization.
    """
    resolved_action_ids: list[str] = []
    for action in list(ctx.pending_actions):
        if (
            action.source_type == "flag"
            and action.source_id == flag_id
            and action.status == HumanActionStatus.PENDING.value
        ):
            resolved = resolve_action(
                ctx,
                action_id=action.action_id,
                decision=decision,
                note=note,
            )
            resolved_action_ids.append(resolved.action_id)
    return resolved_action_ids


def resolve_actions_for_evidence(
    ctx: ProjectContext,
    *,
    evidence_id: str,
    decision: str = "verify_evidence",
    note: str = "",
) -> list[str]:
    """核验证据后，自动关闭直接引用该 evidence_id 的低可信证据动作。

    只自动关闭 source_type=evidence_low_credibility 的动作；
    evidence_gap 表示高风险结论没有 evidence_id，不能因为某条证据被核验而误关。
    """
    resolved_action_ids: list[str] = []
    for action in list(ctx.pending_actions):
        if (
            action.status != HumanActionStatus.PENDING.value
            or action.action_type != "verify_evidence"
            or action.source_type
            not in {"evidence_low_credibility", "evidence_unverified_for_high_risk"}
        ):
            continue

        payload = action.payload_before or {}
        sources = list(payload.get("weak_sources", []) or []) + list(
            payload.get("unverified_sources", []) or []
        )
        matched = any(
            isinstance(source, dict) and source.get("evidence_id") == evidence_id
            for source in sources
        )
        if not matched:
            continue

        resolved = resolve_action(
            ctx,
            action_id=action.action_id,
            decision=decision,
            note=note or f"Evidence {evidence_id} verified.",
        )
        resolved_action_ids.append(resolved.action_id)
    return resolved_action_ids


def supersede_actions_for_stage(
    ctx: ProjectContext,
    *,
    stage: int,
    reason: str,
    superseded_by: str | None = None,
) -> int:
    """
    阶段重跑或回退时废弃旧动作，避免 resolved/reject 的历史动作永久阻断新版本。
    已批准/已核验的 resolved 动作保留为历史，不再阻断。
    """
    count = 0
    now = datetime.utcnow()
    key_statuses = {HumanActionStatus.PENDING.value}
    for action in ctx.pending_actions:
        if action.stage_id != stage:
            continue
        should_supersede = action.status in key_statuses or (
            action.status == HumanActionStatus.RESOLVED.value
            and action.reviewer_decision == "reject"
            and action.action_type in {"approve", "edit", "escalate"}
        )
        if not should_supersede:
            continue

        before = action.model_dump(mode="json")
        action.status = HumanActionStatus.SUPERSEDED.value
        action.reviewer_note = reason
        action.superseded_by = superseded_by
        if action.resolved_at is None:
            action.resolved_at = now
        append_audit_event(
            ctx,
            actor="system",
            event_type="human_action_superseded",
            target_type="human_action",
            target_id=action.action_id,
            before=before,
            after=action,
            metadata={"reason": reason, "stage_id": stage, "superseded_by": superseded_by},
        )
        # Do not call graph.interrupts here. Interrupt records are synchronized
        # by graph.interrupts.sync_interrupt_records() in the execution adapter,
        # or explicitly by core.execution_service after API-level action
        # resolution. This keeps the business service independent of execution
        # mode.
        count += 1
    return count


def cancel_pending_actions_for_stage(
    ctx: ProjectContext,
    *,
    stage: int,
    reason: str,
) -> int:
    """兼容旧调用名：现在实际执行 supersede。"""
    return supersede_actions_for_stage(ctx, stage=stage, reason=reason)


def format_pending_actions_for_review(ctx: ProjectContext, stage: int) -> tuple[int, str]:
    """生成审核提示中展示的人工动作摘要。"""
    actions = ctx.get_pending_actions(stage)
    if not actions:
        return 0, "无。"

    lines = []
    for action in actions:
        blocking = "阻断" if action.blocking else "非阻断"
        lines.append(
            f"- `{action.action_id}` v{action.stage_output_version} "
            f"[{action.risk_level}/{action.action_type}/{blocking}] "
            f"{action.title}：{action.trigger_reason or action.description}"
        )
    return len(actions), "\n".join(lines)
