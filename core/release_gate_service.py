# core/release_gate_service.py
"""Read-only release gate decision for external deployment pipelines.

This module deliberately reuses the authoritative approval readiness and
``effective_approval_status`` logic. It never mutates the context, never calls
the gate engine, never calls an LLM, and never executes a target system.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from core.approval_service import (
    ReleaseBlocker,
    build_release_readiness,
    effective_approval_status,
    latest_approval,
)
from core.evaluation_version import current_evaluation_digest
from core.models import ProjectContext
from core.release_evidence import release_evidence_digest

ReleaseGateReasonCode = Literal[
    "approved",
    "not_applicable",
    "approval_not_requested",
    "approval_rejected",
    "approval_stale",
    "approval_invalidated",
    "prerequisites_not_met",
    "gate_unavailable",
]

_REASON_BY_STATUS: dict[str, ReleaseGateReasonCode] = {
    "approved": "approved",
    "not_requested": "approval_not_requested",
    "rejected": "approval_rejected",
    "stale": "approval_stale",
    "invalidated": "approval_invalidated",
}

_DEFAULT_BLOCKER_MESSAGES: dict[ReleaseGateReasonCode, str] = {
    "not_applicable": "该会话不是业务会话，不适用上线批准。",
    "approval_not_requested": "尚未申请上线批准。",
    "approval_rejected": "最近一次上线批准被拒绝。",
    "approval_stale": "评估内容已变化，原上线批准已过期。",
    "approval_invalidated": "发布证据或前置条件已变化，原上线批准已失效。",
    "prerequisites_not_met": "上线前置条件不再满足。",
    "gate_unavailable": "发布门禁当前不可用。",
}

_MAX_REASON_DETAIL_CHARS = 500


class ReleaseGateNotFoundError(LookupError):
    """Session does not exist or belongs to another tenant."""


class ReleaseGateUnavailableError(RuntimeError):
    """The gate decision or its audit row could not be persisted."""


class ReleaseGateDecision(BaseModel):
    decision: Literal["allow", "block"]
    reason_code: ReleaseGateReasonCode
    reason_detail: str = ""
    approval_status: str
    applicable: bool
    session_id: str
    approval_id: str = ""
    evaluation_version_digest: str = ""
    evidence_digest: str = ""
    release_batch_id: str = ""
    required_test_eval_ids: list[str] = Field(default_factory=list)
    blockers: list[ReleaseBlocker] = Field(default_factory=list)
    checked_at: datetime
    check_id: str = ""


def _status_blocker(
    reason_code: ReleaseGateReasonCode, detail: str, approval_id: str
) -> ReleaseBlocker:
    message = detail.strip() or _DEFAULT_BLOCKER_MESSAGES[reason_code]
    return ReleaseBlocker(
        code=reason_code,
        message=message[:_MAX_REASON_DETAIL_CHARS],
        severity="high",
        source_type="project_approval",
        source_id=approval_id or None,
        required_resolution="request_release_approval",
    )


def _not_applicable_blocker(session_id: str) -> ReleaseBlocker:
    return ReleaseBlocker(
        code="not_applicable",
        message=_DEFAULT_BLOCKER_MESSAGES["not_applicable"],
        severity="high",
        source_type="session",
        source_id=session_id,
        required_resolution="",
    )


def evaluate_release_gate(ctx: ProjectContext) -> ReleaseGateDecision:
    """Compute one live release decision without mutating the project context."""
    readiness = build_release_readiness(ctx)
    if not readiness.applicable:
        return ReleaseGateDecision(
            decision="block",
            reason_code="not_applicable",
            reason_detail="public_demo",
            approval_status="not_requested",
            applicable=False,
            session_id=ctx.session_id,
            blockers=[_not_applicable_blocker(ctx.session_id)],
            checked_at=datetime.now(UTC),
        )

    digest = current_evaluation_digest(ctx)
    latest = latest_approval(ctx)
    evidence_digest = release_evidence_digest(
        ctx,
        batch_run_ids=readiness.release_batch_run_ids,
        required_eval_ids=readiness.required_test_eval_ids,
        evaluation_digest=digest,
    )
    status, reason = effective_approval_status(
        ctx,
        latest,
        readiness=readiness,
        evidence_digest=evidence_digest,
    )
    reason_code = _REASON_BY_STATUS.get(status, "approval_invalidated")
    if status == "approved" and not readiness.can_approve:
        reason_code = "prerequisites_not_met"

    blockers = list(readiness.blockers)
    if reason_code != "approved" and not blockers:
        blockers = [
            _status_blocker(
                reason_code,
                reason,
                latest.approval_id if latest else "",
            )
        ]

    decision: Literal["allow", "block"] = (
        "allow" if reason_code == "approved" and readiness.can_approve else "block"
    )
    return ReleaseGateDecision(
        decision=decision,
        reason_code=reason_code,
        reason_detail=(reason or "")[:_MAX_REASON_DETAIL_CHARS],
        approval_status=status,
        applicable=True,
        session_id=ctx.session_id,
        approval_id=latest.approval_id if latest else "",
        evaluation_version_digest=digest,
        evidence_digest=evidence_digest,
        release_batch_id=readiness.release_batch_id,
        required_test_eval_ids=list(readiness.required_test_eval_ids),
        blockers=blockers,
        checked_at=datetime.now(UTC),
    )
