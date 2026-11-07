# core/approval_service.py
"""Independent release (go-live) approval.

Report generation, assessment completion, and release approval are distinct:

- report artifacts record what the assessment produced;
- ``SessionState.COMPLETE`` means the assessment finished;
- a :class:`ProjectApproval` records an independent admin decision that the
  project may go live, bound to the current evaluation version.

The readiness evaluation is read-only. It deliberately does not call the gate
engine because gate evaluation persists records and may materialize actions.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.audit_service import append_audit_event
from core.coverage.policy import required_high_risk_node_ids
from core.evaluation_version import current_evaluation_digest, current_evaluation_version
from core.models import (
    HumanActionStatus,
    ProjectApproval,
    ProjectContext,
    SessionState,
)
from core.release_evidence import (
    build_release_evidence,
    release_evidence_digest,
    release_run_reasons,
)
from core.risk_treatment_service import (
    is_business_session,
    treatment_blockers,
)

RELEASE_APPROVER_ROLE = "admin"

logger = logging.getLogger(__name__)


class ReleaseApprovalAuthorizationError(PermissionError):
    """Reviewer role, identity, or independence cannot be verified."""


class ReleaseApprovalNotApplicableError(ValueError):
    """Closure approval does not apply to public_demo sessions."""


class ReleaseApprovalPrerequisiteError(ValueError):
    """One or more release prerequisites are not met."""

    def __init__(self, blockers: list[ReleaseBlocker]) -> None:
        super().__init__("Release approval prerequisites are not met")
        self.blockers = blockers


class ReleaseBlocker(BaseModel):
    code: str
    message: str
    severity: Literal["low", "medium", "high", "critical"] = "high"
    source_type: str | None = None
    source_id: str | None = None
    required_resolution: str = ""


class ReleaseReadiness(BaseModel):
    applicable: bool
    exempt_reason: str = ""
    evaluation_completed: bool = False
    can_approve: bool = False
    blockers: list[ReleaseBlocker] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    required_test_node_ids: list[str] = Field(default_factory=list)
    required_test_eval_ids: list[str] = Field(default_factory=list)
    release_batch_id: str = ""
    release_batch_run_ids: list[str] = Field(default_factory=list)
    release_batch_eval_ids: list[str] = Field(default_factory=list)
    passed_real_test_node_ids: list[str] = Field(default_factory=list)
    evaluation_version: dict[str, Any] = Field(default_factory=dict)


def _current_stage_version(ctx: ProjectContext, stage: int) -> int:
    return int(ctx.stage_output_versions.get(f"stage_{stage}", 1))


def _stage_outputs_present(ctx: ProjectContext) -> bool:
    return all(getattr(ctx, f"stage_{stage}_output", None) is not None for stage in range(1, 5))


def _stale_stage_keys(ctx: ProjectContext) -> list[str]:
    return [
        key
        for key, value in (getattr(ctx, "stage_staleness", {}) or {}).items()
        if isinstance(value, dict) and value.get("stale")
    ]


def _parser_error_keys(ctx: ProjectContext) -> list[str]:
    return [key for key, value in ctx.parser_errors.items() if key.startswith("stage_") and value]


def _pending_blocking_actions(ctx: ProjectContext) -> list[str]:
    action_ids: list[str] = []
    for action in ctx.pending_actions:
        if action.status != HumanActionStatus.PENDING.value or not action.blocking:
            continue
        if action.stage_output_version != _current_stage_version(ctx, action.stage_id):
            continue
        action_ids.append(action.action_id)
    return action_ids


def _open_high_critical_safety(ctx: ProjectContext) -> list[str]:
    return [
        finding.finding_id
        for finding in ctx.safety_findings
        if finding.status == "open" and finding.severity in {"high", "critical"}
    ]


def _evidence_blockers(ctx: ProjectContext) -> list[ReleaseBlocker]:
    blockers: list[ReleaseBlocker] = []
    evidence_by_id = {evidence.evidence_id: evidence for evidence in ctx.evidence_sources}
    if not ctx.stage_1_output:
        return blockers

    for failure_mode in ctx.stage_1_output.failure_modes:
        if str(failure_mode.severity).lower() not in {"high", "critical"}:
            continue
        evidence_ids = list(dict.fromkeys(failure_mode.evidence_ids or []))
        if not evidence_ids:
            blockers.append(
                ReleaseBlocker(
                    code="unverified_evidence",
                    message=f"高风险失败模式 {failure_mode.id} 没有证据引用，无法支持上线批准。",
                    severity=failure_mode.severity,
                    source_type="failure_mode",
                    source_id=failure_mode.id,
                    required_resolution="edit_stage_output",
                )
            )
            continue
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                blockers.append(
                    ReleaseBlocker(
                        code="unverified_evidence",
                        message=(
                            f"高风险失败模式 {failure_mode.id} 引用了不存在的证据 {evidence_id}。"
                        ),
                        severity=failure_mode.severity,
                        source_type="evidence",
                        source_id=evidence_id,
                        required_resolution="edit_stage_output",
                    )
                )
                continue
            if not evidence.verified:
                blockers.append(
                    ReleaseBlocker(
                        code="unverified_evidence",
                        message=(
                            f"高风险失败模式 {failure_mode.id} 引用的证据 {evidence_id} "
                            "尚未人工核验，不能作为上线依据。"
                        ),
                        severity=failure_mode.severity,
                        source_type="evidence",
                        source_id=evidence_id,
                        required_resolution="verify_evidence",
                    )
                )
    return blockers


def _valid_real_target_runs(ctx: ProjectContext, digest: str) -> list[Any]:
    cases = {case.eval_id: case for case in ctx.eval_cases}
    return [
        run
        for run in ctx.eval_runs
        if not release_run_reasons(
            ctx,
            run,
            cases.get(run.eval_id),
            evaluation_digest=digest,
        )
    ]


def _to_blocker(item: dict[str, Any]) -> ReleaseBlocker:
    severity = str(item.get("severity") or "high")
    if severity not in {"low", "medium", "high", "critical"}:
        severity = "high"
    return ReleaseBlocker(
        code=str(item["code"]),
        message=str(item["message"]),
        severity=severity,  # type: ignore[arg-type]
        source_type=item.get("source_type"),
        source_id=item.get("source_id"),
        required_resolution=str(item.get("required_resolution") or ""),
    )


def build_release_readiness(ctx: ProjectContext) -> ReleaseReadiness:
    """Compute release prerequisites without mutating or persisting anything."""
    applicable = is_business_session(ctx)
    if not applicable:
        return ReleaseReadiness(
            applicable=False,
            exempt_reason="public_demo",
            evaluation_completed=ctx.current_state == SessionState.COMPLETE,
            can_approve=False,
            checks={"applicable": False},
            evaluation_version=current_evaluation_version(ctx),
        )

    digest = current_evaluation_digest(ctx)
    evaluation_version = current_evaluation_version(ctx)
    blockers: list[ReleaseBlocker] = []

    evaluation_completed = (
        ctx.current_state == SessionState.COMPLETE
        and _stage_outputs_present(ctx)
        and not _stale_stage_keys(ctx)
    )
    if ctx.current_state != SessionState.COMPLETE:
        blockers.append(
            ReleaseBlocker(
                code="evaluation_not_completed",
                message="评估流程尚未完成（当前状态不是 complete），不能获得上线批准。",
                severity="high",
                source_type="session",
                source_id=ctx.session_id,
                required_resolution="run_stage",
            )
        )
    elif not _stage_outputs_present(ctx):
        blockers.append(
            ReleaseBlocker(
                code="missing_stage_output",
                message="存在缺失的阶段输出，评估尚未完成。",
                severity="high",
                source_type="stage",
                source_id=None,
                required_resolution="run_stage",
            )
        )

    stale_keys = _stale_stage_keys(ctx)
    if stale_keys:
        blockers.append(
            ReleaseBlocker(
                code="stale_stage",
                message=f"存在过期阶段输出：{', '.join(sorted(stale_keys))}，需重新评估。",
                severity="high",
                source_type="stage",
                source_id=", ".join(sorted(stale_keys)),
                required_resolution="rerun_stage",
            )
        )

    pending_actions = _pending_blocking_actions(ctx)
    if pending_actions:
        blockers.append(
            ReleaseBlocker(
                code="pending_action",
                message=f"仍有 {len(pending_actions)} 条当前版本的阻断型人工动作未处理。",
                severity="high",
                source_type="human_action",
                source_id=pending_actions[0],
                required_resolution="resolve_action",
            )
        )

    parser_errors = _parser_error_keys(ctx)
    if parser_errors:
        blockers.append(
            ReleaseBlocker(
                code="parser_error",
                message=f"仍有未修复的结构化解析错误：{', '.join(parser_errors)}。",
                severity="high",
                source_type="parser",
                source_id=parser_errors[0],
                required_resolution="edit_stage_output",
            )
        )

    open_safety = _open_high_critical_safety(ctx)
    if open_safety:
        blockers.append(
            ReleaseBlocker(
                code="safety_finding",
                message=f"仍有 {len(open_safety)} 个高危/危急安全发现未关闭。",
                severity="critical",
                source_type="safety_finding",
                source_id=open_safety[0],
                required_resolution="resolve_safety_finding",
            )
        )

    evidence_blockers = _evidence_blockers(ctx)
    blockers.extend(evidence_blockers)

    for item in treatment_blockers(ctx):
        blockers.append(
            ReleaseBlocker(
                code=item["code"],
                message=item["message"],
                severity=item["risk_level"],
                source_type=item["source_type"],
                source_id=item["source_id"],
                required_resolution=item["required_resolution"],
            )
        )

    required_nodes = sorted(required_high_risk_node_ids(ctx))
    evidence = build_release_evidence(ctx, evaluation_digest=digest)
    blockers.extend(_to_blocker(item) for item in evidence.blockers)
    required_eval_ids = [case.eval_id for case in evidence.required_cases]
    valid_runs = _valid_real_target_runs(ctx, digest)
    passed_nodes = sorted(
        {run.target_node_id for run in valid_runs if run.target_node_id is not None}
    )
    blocker_codes = {blocker.code for blocker in blockers}
    release_batch = evidence.release_batch

    checks = {
        "applicable": True,
        "evaluation_completed": evaluation_completed,
        "no_stale_stage_outputs": not stale_keys,
        "no_pending_blocking_actions": not pending_actions,
        "no_parser_errors": not parser_errors,
        "no_open_high_critical_safety_findings": not open_safety,
        "verified_adopted_evidence": not evidence_blockers,
        "risk_treatments_complete": not treatment_blockers(ctx),
        "target_deployment_declared": "target_deployment" not in blocker_codes,
        "required_test_cases_defined": "required_test_case" not in blocker_codes,
        "release_batch_complete": release_batch is not None,
        "real_target_tests_passed": (
            "real_target_test" not in blocker_codes and release_batch is not None
        ),
    }
    can_approve = all(checks.values())

    return ReleaseReadiness(
        applicable=True,
        evaluation_completed=evaluation_completed,
        can_approve=can_approve,
        blockers=blockers,
        checks=checks,
        required_test_node_ids=required_nodes,
        required_test_eval_ids=required_eval_ids,
        release_batch_id=release_batch.experiment_id if release_batch else "",
        release_batch_run_ids=list(release_batch.run_ids) if release_batch else [],
        release_batch_eval_ids=list(release_batch.eval_ids) if release_batch else [],
        passed_real_test_node_ids=passed_nodes,
        evaluation_version=evaluation_version,
    )


def _record_approval_metric(decision: str) -> None:
    try:
        from api.metrics import record_release_approval

        record_release_approval(decision)
    except Exception:  # pragma: no cover - metrics must never break approvals
        logger.debug("record_release_approval failed; non-fatal", exc_info=True)


def _log_approval_denied(ctx: ProjectContext, reason: str, actor_role: str) -> None:
    """审批拒绝日志：只记录固定原因码与角色，不记录 note 或身份明文。"""
    logger.warning(
        "release_approval_denied",
        extra={
            "event": "release_approval_denied",
            "session_id": ctx.session_id,
            "reason": reason,
            "actor_role": actor_role or "unknown",
        },
    )
    _record_approval_metric("denied")


def _log_approval_decided(
    ctx: ProjectContext,
    approval: ProjectApproval,
    actor_role: str,
    *,
    superseded_count: int = 0,
) -> None:
    logger.info(
        "release_approval_decided",
        extra={
            "event": "release_approval_decided",
            "session_id": ctx.session_id,
            "approval_id": approval.approval_id,
            "status": approval.status,
            "actor_role": actor_role or "unknown",
            "superseded_count": superseded_count,
        },
    )


def _assert_approval_authorized(ctx: ProjectContext, actor_id: str, actor_role: str) -> str:
    reviewer = (actor_id or "").strip()
    if actor_role != RELEASE_APPROVER_ROLE:
        _log_approval_denied(ctx, "role_not_admin", actor_role)
        raise ReleaseApprovalAuthorizationError("Release approval requires admin role")
    if not reviewer:
        _log_approval_denied(ctx, "missing_reviewer", actor_role)
        raise ReleaseApprovalAuthorizationError("Reviewer identity is required")
    creator = (getattr(ctx, "created_by", "") or "").strip()
    if not creator:
        _log_approval_denied(ctx, "missing_creator", actor_role)
        raise ReleaseApprovalAuthorizationError(
            "Session creator is not recorded; reviewer independence cannot be verified"
        )
    if reviewer == creator:
        _log_approval_denied(ctx, "self_approval", actor_role)
        raise ReleaseApprovalAuthorizationError(
            "Self-approval is not allowed: the reviewer is the session creator"
        )
    return reviewer


def _sorted_approvals(ctx: ProjectContext) -> list[ProjectApproval]:
    return sorted(ctx.project_approvals, key=lambda item: item.created_at)


def latest_approval(ctx: ProjectContext) -> ProjectApproval | None:
    approvals = _sorted_approvals(ctx)
    return approvals[-1] if approvals else None


def effective_approval_status(
    ctx: ProjectContext,
    approval: ProjectApproval | None,
    *,
    readiness: ReleaseReadiness | None = None,
    evidence_digest: str | None = None,
) -> tuple[str, str]:
    """Return ``(status, reason)``; stored records stay append-only.

    ``approved`` is only effective while the evaluation digest, the release
    evidence snapshot and all current prerequisites still match. Any later
    treatment rejection, test re-judgment, safety finding or stage change
    invalidates the approval without deleting its history.
    """
    if approval is None:
        return "not_requested", ""
    if approval.status == "rejected":
        return "rejected", ""
    digest = current_evaluation_digest(ctx)
    if approval.evaluation_version_digest != digest:
        return "stale", "evaluation content changed since the approval was granted"
    if not approval.evidence_digest:
        return "invalidated", "approval has no release-evidence binding; re-approval required"
    if readiness is None:
        readiness = build_release_readiness(ctx)
    if evidence_digest is None:
        evidence_digest = release_evidence_digest(
            ctx,
            batch_run_ids=readiness.release_batch_run_ids,
            required_eval_ids=readiness.required_test_eval_ids,
            evaluation_digest=digest,
        )
    if approval.evidence_digest != evidence_digest:
        return (
            "invalidated",
            "release evidence changed after approval (treatment review, test judgment, "
            "safety finding, or blocking action); re-approval required",
        )
    if not readiness.can_approve:
        if readiness.blockers:
            first = readiness.blockers[0]
            return "invalidated", f"当前前置条件不再满足：{first.code} {first.message}"
        return "invalidated", "release prerequisites are no longer satisfied"
    return "approved", ""


def _evidence_digest_for(
    ctx: ProjectContext,
    readiness: ReleaseReadiness,
    digest: str,
) -> str:
    return release_evidence_digest(
        ctx,
        batch_run_ids=readiness.release_batch_run_ids,
        required_eval_ids=readiness.required_test_eval_ids,
        evaluation_digest=digest,
    )


def request_release_approval(
    ctx: ProjectContext,
    *,
    decision: str,
    note: str,
    actor_id: str,
    actor_role: str,
) -> tuple[ProjectApproval, ReleaseReadiness, bool]:
    """Grant or reject release approval and return the decision record."""
    if not is_business_session(ctx):
        _log_approval_denied(ctx, "not_applicable", actor_role)
        raise ReleaseApprovalNotApplicableError(
            "Release approval is not applicable to public_demo sessions"
        )
    if decision not in {"approve", "reject"}:
        _log_approval_denied(ctx, "invalid_decision", actor_role)
        raise ValueError(f"Unsupported release approval decision: {decision}")

    reviewer = _assert_approval_authorized(ctx, actor_id, actor_role)
    readiness = build_release_readiness(ctx)
    digest = current_evaluation_digest(ctx)
    evidence_digest = _evidence_digest_for(ctx, readiness, digest)

    if decision == "reject":
        approval = ProjectApproval(
            session_id=ctx.session_id,
            status="rejected",
            evaluation_version_digest=digest,
            evaluation_version=readiness.evaluation_version,
            prerequisites=readiness.model_dump(mode="json"),
            requested_by=reviewer,
            decided_by=reviewer,
            decided_role=actor_role,
            decision_note=note,
            evidence_digest=evidence_digest,
        )
        ctx.project_approvals.append(approval)
        append_audit_event(
            ctx,
            actor="user",
            event_type="release_approval_rejected",
            target_type="project_approval",
            target_id=approval.approval_id,
            after=approval,
            metadata={
                "reviewer_id": reviewer,
                "reviewer_role": actor_role,
                "evaluation_version_digest": digest,
                "evidence_digest": evidence_digest,
                "release_batch_id": readiness.release_batch_id,
                "blockers_count": len(readiness.blockers),
            },
        )
        _log_approval_decided(ctx, approval, actor_role)
        _record_approval_metric("rejected")
        return approval, readiness, False

    if not readiness.can_approve:
        _log_approval_denied(ctx, "prerequisites_not_met", actor_role)
        raise ReleaseApprovalPrerequisiteError(readiness.blockers)

    latest = latest_approval(ctx)
    if (
        latest is not None
        and latest.status == "approved"
        and latest.evaluation_version_digest == digest
        and latest.evidence_digest == evidence_digest
    ):
        logger.info(
            "release_approval_unchanged",
            extra={
                "event": "release_approval_unchanged",
                "session_id": ctx.session_id,
                "approval_id": latest.approval_id,
                "actor_role": actor_role or "unknown",
            },
        )
        return latest, readiness, True

    approval = ProjectApproval(
        session_id=ctx.session_id,
        status="approved",
        evaluation_version_digest=digest,
        evaluation_version=readiness.evaluation_version,
        prerequisites=readiness.model_dump(mode="json"),
        requested_by=reviewer,
        decided_by=reviewer,
        decided_role=actor_role,
        decision_note=note,
        evidence_digest=evidence_digest,
    )
    ctx.project_approvals.append(approval)
    superseded = [
        item.approval_id
        for item in ctx.project_approvals
        if item.status == "approved" and item.approval_id != approval.approval_id
    ]
    append_audit_event(
        ctx,
        actor="user",
        event_type="release_approval_granted",
        target_type="project_approval",
        target_id=approval.approval_id,
        after=approval,
        metadata={
            "reviewer_id": reviewer,
            "reviewer_role": actor_role,
            "evaluation_version_digest": digest,
            "evidence_digest": evidence_digest,
            "release_batch_id": readiness.release_batch_id,
            "release_batch_run_ids": readiness.release_batch_run_ids,
            "superseded_approval_ids": superseded,
        },
    )
    _log_approval_decided(ctx, approval, actor_role, superseded_count=len(superseded))
    _record_approval_metric("granted")
    return approval, readiness, False


def _report_generation_status(ctx: ProjectContext) -> dict[str, Any]:
    artifacts = sorted(
        ctx.report_artifacts,
        key=lambda artifact: artifact.generated_at,
    )
    latest = artifacts[-1] if artifacts else None
    return {
        "artifact_count": len(artifacts),
        "latest_report_id": latest.report_id if latest else "",
        "generated_at": latest.generated_at.isoformat() if latest else "",
        "is_approval": False,
        "notice": "报告生成/导出不代表上线批准",
    }


def build_approval_summary(
    ctx: ProjectContext,
    readiness: ReleaseReadiness | None = None,
) -> dict[str, Any]:
    """Three explicitly separated statuses plus the effective release decision."""
    applicable = is_business_session(ctx)
    digest = current_evaluation_digest(ctx)
    readiness = readiness or build_release_readiness(ctx)
    evidence_digest = _evidence_digest_for(ctx, readiness, digest)
    latest = latest_approval(ctx)
    status, reason = effective_approval_status(
        ctx,
        latest,
        readiness=readiness,
        evidence_digest=evidence_digest,
    )
    is_release_approved = status == "approved"

    return {
        "applicable": applicable,
        "exempt_reason": "" if applicable else "public_demo",
        "evaluation_version": current_evaluation_version(ctx),
        "report_generation": _report_generation_status(ctx),
        "evaluation_completion": {
            "completed": ctx.current_state == SessionState.COMPLETE and _stage_outputs_present(ctx),
            "current_state": getattr(ctx.current_state, "value", str(ctx.current_state)),
        },
        "release_approval": {
            "status": status,
            "approval_id": latest.approval_id if latest else "",
            "stored_status": latest.status if latest else "",
            "decided_by": latest.decided_by if latest else "",
            "decided_role": latest.decided_role if latest else "",
            "decided_at": latest.created_at.isoformat() if latest else "",
            "decision_note": latest.decision_note if latest else "",
            "evaluation_version_digest": latest.evaluation_version_digest if latest else "",
            "evidence_digest": latest.evidence_digest if latest else "",
            "release_batch_id": (
                str(latest.prerequisites.get("release_batch_id") or "")
                if latest
                else readiness.release_batch_id
            ),
            "required_test_eval_ids": list(readiness.required_test_eval_ids),
            "is_current": status == "approved",
            "invalidated_reason": reason if status == "invalidated" else "",
            "is_invalidated": status in {"stale", "invalidated"},
            "stale_reason": reason,
        },
        "history_count": len(ctx.project_approvals),
        "is_release_approved": is_release_approved,
    }


def list_project_approvals(ctx: ProjectContext) -> list[dict[str, Any]]:
    """Append-only approval history annotated with effective status."""
    digest = current_evaluation_digest(ctx)
    readiness = build_release_readiness(ctx)
    evidence_digest = _evidence_digest_for(ctx, readiness, digest)
    rows: list[dict[str, Any]] = []
    for approval in _sorted_approvals(ctx):
        status, reason = effective_approval_status(
            ctx,
            approval,
            readiness=readiness,
            evidence_digest=evidence_digest,
        )
        rows.append(
            {
                **approval.model_dump(mode="json"),
                "effective_status": status,
                "stale_reason": reason,
            }
        )
    return rows
