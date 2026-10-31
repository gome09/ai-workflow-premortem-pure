# core/governance/action_state.py
"""Human-action state helpers: idempotent creation, logs, and versions."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, cast

from core.audit_service import append_audit_event
from core.models import ActionResolutionLog, HumanActionStatus, PendingHumanAction, ProjectContext

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
        action_type=cast(
            Literal["approve", "edit", "reject", "verify_evidence", "escalate"], action_type
        ),
        title=title,
        description=description,
        risk_level=cast(Literal["low", "medium", "high", "critical"], risk_level),
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
