# core/governance/action_resolution.py
"""Human-action resolution state machine, logs, and review summaries."""

from __future__ import annotations

from datetime import datetime

from core.audit_service import append_audit_event
from core.governance.action_effects import (
    apply_post_resolution_effects,
    apply_pre_resolution_effects,
)
from core.governance.action_state import (
    _action_resolution_log_exists,
    _append_action_resolution_log,
    _latest_action_resolution_log,
    _stable_hash,
    _target_object_exists,
    current_stage_output_version,
)
from core.models import (
    ActionResolutionResult,
    HumanActionStatus,
    PendingHumanAction,
    ProjectContext,
)
from graph.transition_policy import assert_action_resolution_allowed


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
    from core.audit_service import append_audit_event

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

            pre_effects = apply_pre_resolution_effects(
                ctx,
                action,
                decision=decision,
                payload_after=payload_after,
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

            post_effects = apply_post_resolution_effects(
                ctx,
                action,
                decision=decision,
                note=note,
                pre_effects=pre_effects,
                payload_after=payload_after,
            )
            if post_effects.skip_resolution_logging:
                continue

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
        error_log = _latest_action_resolution_log(ctx, action_id, effective_idempotency_key)
        result_status = "validation_failed" if action.action_type == "edit" else "error"
        if error_log and error_log.result_status in {
            "validation_failed",
            "conflict",
            "stale",
            "error",
        }:
            result_status = error_log.result_status
        return ActionResolutionResult(
            session_id=ctx.session_id,
            action_id=action_id,
            requested_status=decision,
            result_status=result_status,  # type: ignore[arg-type]
            action_status=action.status,
            before_hash=before_hash,
            after_hash=error_log.after_hash if error_log else None,
            log_id=error_log.log_id if error_log else None,
            error_message=str(exc),
        )

    logs = getattr(ctx, "action_resolution_logs", []) or []
    new_logs = logs[before_log_count:]
    final_log = (
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
        log_id=final_log.log_id if final_log else None,
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


_RISK_LABEL = {"critical": "危急", "high": "高", "medium": "中", "low": "低"}

_ACTION_SOURCE_LABEL = {
    "flag": "有内容需要人工核验",
    "failure_mode": "有高风险失败模式需要确认",
    "evidence_gap": "证据引用不足，需要补充",
    "evidence_low_credibility": "有证据可信度偏低，需要核验",
    "evidence_unverified_for_high_risk": "高风险结论的证据尚未核验",
    "oversight_policy": "有工作流节点的监督策略需要处理",
    "stress_test": "压力测试结果需要人工决定",
    "eval_coverage": "高风险节点缺少测试用例覆盖",
    "eval_case": "有测试用例未通过，需要处理",
    "eval_run": "有测试运行结果需要人工复核",
    "trigger_method": "有触发方式需要人工审核确认",
    "safety_finding": "有安全风险需要处理",
    "parser": "AI 输出解析失败，需要人工修复",
}


def format_pending_actions_for_review(ctx: ProjectContext, stage: int) -> tuple[int, str]:
    """生成审核提示中展示的人工动作摘要（自然语言，不含内部 ID）。"""
    actions = ctx.get_pending_actions(stage)
    if not actions:
        return 0, "无。"

    grouped: dict[str, dict] = {}
    for action in actions:
        key = action.source_type or "human_action"
        entry = grouped.setdefault(key, {"count": 0, "risks": set(), "blocking": False})
        entry["count"] += 1
        entry["risks"].add(action.risk_level)
        entry["blocking"] = entry["blocking"] or action.blocking

    lines = []
    for source_type, info in grouped.items():
        label = _ACTION_SOURCE_LABEL.get(source_type, "有事项需要人工处理")
        risk_label = "、".join(_RISK_LABEL.get(r, r) for r in sorted(info["risks"], key=str))
        count_note = f"（{info['count']} 项）" if info["count"] > 1 else ""
        blocking_note = "" if info["blocking"] else "（不阻断推进）"
        lines.append(f"- {label}{count_note}{blocking_note}，风险等级：{risk_label}")
    return len(actions), "\n".join(lines)
