# core/risk_treatment_service.py
"""Accountable treatment plans for high/critical risk items.

This module is pure domain logic: it never creates or resolves
``PendingHumanAction`` records. Treatment gaps are surfaced as stage blockers
whose resolution operation points at the risk-treatment API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from core.audit_service import append_audit_event
from core.evaluation_version import current_evaluation_digest
from core.models import ProjectContext, RiskTreatment

TREATMENT_FINAL_STATUSES = {"completed", "accepted"}
TREATMENT_WRITE_ROLES = {"editor", "admin"}
BUSINESS_CLASSIFICATIONS = {"business_internal", "sensitive_personal"}

RiskTreatmentDecision = Literal["accept", "reject"]


class RiskTreatmentError(ValueError):
    """Invalid treatment input or source item."""


class RiskTreatmentAuthorizationError(PermissionError):
    """Reviewer role or independence cannot be verified."""


class RiskTreatmentStaleError(ValueError):
    """The evaluation version changed since the treatment was recorded."""


@dataclass(frozen=True)
class TreatmentRequirement:
    source_type: Literal["failure_mode", "safety_finding"]
    source_id: str
    risk_level: Literal["high", "critical"]
    title: str
    description: str


def is_business_session(ctx: ProjectContext) -> bool:
    """Closure requirements apply only to real business sessions."""
    return getattr(ctx, "data_classification", "business_internal") in BUSINESS_CLASSIFICATIONS


def high_risk_treatment_requirements(ctx: ProjectContext) -> list[TreatmentRequirement]:
    """High/critical failure modes plus open high/critical safety findings."""
    requirements: list[TreatmentRequirement] = []
    seen: set[tuple[str, str]] = set()

    if ctx.stage_1_output:
        for failure_mode in ctx.stage_1_output.failure_modes:
            severity = str(failure_mode.severity).lower()
            if severity not in {"high", "critical"}:
                continue
            key = ("failure_mode", failure_mode.id)
            if key in seen:
                continue
            seen.add(key)
            requirements.append(
                TreatmentRequirement(
                    source_type="failure_mode",
                    source_id=failure_mode.id,
                    risk_level=severity,  # type: ignore[arg-type]
                    title=failure_mode.category,
                    description=failure_mode.description,
                )
            )

    for finding in ctx.safety_findings:
        if finding.status != "open" or finding.severity not in {"high", "critical"}:
            continue
        key = ("safety_finding", finding.finding_id)
        if key in seen:
            continue
        seen.add(key)
        requirements.append(
            TreatmentRequirement(
                source_type="safety_finding",
                source_id=finding.finding_id,
                risk_level=finding.severity,
                title=finding.risk_type,
                description=finding.description,
            )
        )

    return requirements


def _latest_treatment(
    ctx: ProjectContext,
    source_type: str,
    source_id: str,
) -> RiskTreatment | None:
    matches = [
        treatment
        for treatment in ctx.risk_treatments
        if treatment.source_type == source_type and treatment.source_id == source_id
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: item.updated_at)[-1]


def evaluate_treatment(treatment: RiskTreatment | None, *, current_digest: str) -> str:
    """Return one deterministic evaluation state for a treatment."""
    if treatment is None:
        return "missing"
    if not (treatment.owner or "").strip() or not (treatment.mitigation_plan or "").strip():
        return "incomplete_fields"
    if treatment.evaluation_version_digest != current_digest:
        return "stale"
    if treatment.status not in TREATMENT_FINAL_STATUSES:
        return "not_final"
    if not (treatment.reviewed_by or "").strip():
        return "unreviewed"
    return "complete"


def treatment_blockers(ctx: ProjectContext) -> list[dict[str, Any]]:
    """Read-only blockers for release readiness and the Stage 4 gate."""
    if not is_business_session(ctx):
        return []

    current_digest = current_evaluation_digest(ctx)
    blockers: list[dict[str, Any]] = []
    for requirement in high_risk_treatment_requirements(ctx):
        treatment = _latest_treatment(ctx, requirement.source_type, requirement.source_id)
        state = evaluate_treatment(treatment, current_digest=current_digest)
        if state == "complete":
            continue
        blockers.append(
            {
                "code": "risk_treatment",
                "gap_type": state,
                "source_type": requirement.source_type,
                "source_id": requirement.source_id,
                "risk_level": requirement.risk_level,
                "message": _blocker_message(requirement, state),
                "required_resolution": "complete_risk_treatment",
                "treatment_id": treatment.treatment_id if treatment else "",
            }
        )
    return blockers


def _blocker_message(requirement: TreatmentRequirement, state: str) -> str:
    if state == "missing":
        return f"高风险项 {requirement.source_id} 缺少风险处置记录：必须指定责任人并提交缓解措施。"
    if state == "incomplete_fields":
        return f"高风险项 {requirement.source_id} 的处置记录缺少责任人或有意义的缓解措施。"
    if state == "stale":
        return (
            f"高风险项 {requirement.source_id} 的处置记录绑定的是旧评估版本，"
            "关键评估内容已变化，需重新提交并复核。"
        )
    if state == "not_final":
        return (
            f"高风险项 {requirement.source_id} 的处置尚未完成（状态必须为 completed 或 accepted）。"
        )
    return f"高风险项 {requirement.source_id} 的处置尚未经独立复核。"


def _find_requirement(
    ctx: ProjectContext, source_type: str, source_id: str
) -> TreatmentRequirement:
    for requirement in high_risk_treatment_requirements(ctx):
        if requirement.source_type == source_type and requirement.source_id == source_id:
            return requirement
    raise RiskTreatmentError(f"Not an open high/critical risk item: {source_type}/{source_id}")


def upsert_risk_treatment(
    ctx: ProjectContext,
    *,
    source_type: str,
    source_id: str,
    owner: str,
    mitigation_plan: str,
    status: str,
    actor_id: str,
    actor_role: str,
    note: str = "",
) -> RiskTreatment:
    """Create or update the treatment record for one high/critical item."""
    if actor_role not in TREATMENT_WRITE_ROLES:
        raise RiskTreatmentAuthorizationError("Risk treatment updates require editor or admin role")
    if status not in {"planned", "in_progress", "completed", "accepted"}:
        raise RiskTreatmentError(f"Unsupported treatment status: {status}")

    requirement = _find_requirement(ctx, source_type, source_id)
    normalized_owner = (owner or "").strip()
    normalized_plan = (mitigation_plan or "").strip()
    if not normalized_owner:
        raise RiskTreatmentError("Risk treatment owner is required")
    if not normalized_plan:
        raise RiskTreatmentError("Risk treatment mitigation_plan is required")

    now = datetime.utcnow()
    current_digest = current_evaluation_digest(ctx)
    existing = _latest_treatment(ctx, source_type, source_id)
    before = existing.model_dump(mode="json") if existing else None
    content_changed = False
    digest_changed = False

    if existing is None:
        treatment = RiskTreatment(
            session_id=ctx.session_id,
            source_type=requirement.source_type,
            source_id=requirement.source_id,
            risk_level=requirement.risk_level,
            owner=normalized_owner,
            mitigation_plan=normalized_plan,
            status=status,  # type: ignore[arg-type]
            review_note=note,
            evaluation_version_digest=current_digest,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        ctx.risk_treatments.append(treatment)
    else:
        treatment = existing
        content_changed = (
            existing.owner != normalized_owner
            or existing.mitigation_plan != normalized_plan
            or existing.status != status
        )
        digest_changed = existing.evaluation_version_digest != current_digest
        treatment.owner = normalized_owner
        treatment.mitigation_plan = normalized_plan
        treatment.status = status  # type: ignore[assignment]
        treatment.review_note = note
        treatment.evaluation_version_digest = current_digest
        treatment.updated_by = actor_id
        treatment.updated_at = now
        if content_changed or digest_changed:
            # A previous review no longer covers the changed plan or the new
            # evaluation version, even when the fields were resubmitted verbatim.
            treatment.reviewed_by = ""
            treatment.reviewed_at = None

    review_cleared_reason = ""
    if existing is not None:
        if content_changed:
            review_cleared_reason = "content_changed"
        elif digest_changed:
            review_cleared_reason = "evaluation_version_changed"

    append_audit_event(
        ctx,
        actor="user",
        event_type="risk_treatment_upserted",
        target_type="risk_treatment",
        target_id=treatment.treatment_id,
        before=before,
        after=treatment,
        metadata={
            "source_type": source_type,
            "source_id": source_id,
            "status": treatment.status,
            "review_cleared": not treatment.reviewed_by,
            "review_cleared_reason": review_cleared_reason,
            "evaluation_version_digest": treatment.evaluation_version_digest,
            "actor_role": actor_role,
        },
    )
    return treatment


def review_risk_treatment(
    ctx: ProjectContext,
    *,
    treatment_id: str,
    decision: RiskTreatmentDecision,
    note: str,
    actor_id: str,
    actor_role: str,
) -> RiskTreatment:
    """Record an independent review decision for one treatment."""
    if actor_role not in TREATMENT_WRITE_ROLES:
        raise RiskTreatmentAuthorizationError("Risk treatment review requires editor or admin role")
    reviewer = (actor_id or "").strip()
    if not reviewer:
        raise RiskTreatmentAuthorizationError("Reviewer identity is required")

    treatment = next(
        (item for item in ctx.risk_treatments if item.treatment_id == treatment_id), None
    )
    if treatment is None:
        raise RiskTreatmentError(f"Risk treatment not found: {treatment_id}")
    if reviewer == (treatment.updated_by or "").strip():
        raise RiskTreatmentAuthorizationError(
            "Risk treatment reviewer must differ from the last updater"
        )
    if treatment.evaluation_version_digest != current_evaluation_digest(ctx):
        raise RiskTreatmentStaleError(
            "Evaluation content changed since the treatment was recorded; "
            "update the treatment before reviewing it again"
        )

    before = treatment.model_dump(mode="json")
    now = datetime.utcnow()
    if decision == "accept":
        if treatment.status not in TREATMENT_FINAL_STATUSES:
            raise RiskTreatmentError(
                "Treatment status must be completed or accepted before review approval"
            )
        treatment.reviewed_by = reviewer
        treatment.reviewed_at = now
        treatment.review_note = note
    else:
        treatment.status = "in_progress"
        treatment.reviewed_by = ""
        treatment.reviewed_at = None
        treatment.review_note = note
    treatment.updated_at = now

    append_audit_event(
        ctx,
        actor="user",
        event_type="risk_treatment_reviewed",
        target_type="risk_treatment",
        target_id=treatment.treatment_id,
        before=before,
        after=treatment,
        metadata={
            "decision": decision,
            "reviewer_id": reviewer,
            "reviewer_role": actor_role,
            "evaluation_version_digest": treatment.evaluation_version_digest,
        },
    )
    return treatment


def build_risk_treatment_summary(ctx: ProjectContext) -> dict[str, Any]:
    """Coverage summary for reports, API responses, and the closure panel."""
    applicable = is_business_session(ctx)
    current_digest = current_evaluation_digest(ctx)
    requirements = high_risk_treatment_requirements(ctx) if applicable else []

    items: list[dict[str, Any]] = []
    state_counts: dict[str, int] = {}
    for requirement in requirements:
        treatment = _latest_treatment(ctx, requirement.source_type, requirement.source_id)
        state = (
            evaluate_treatment(treatment, current_digest=current_digest)
            if applicable
            else "complete"
        )
        state_counts[state] = state_counts.get(state, 0) + 1
        items.append(
            {
                "requirement": asdict(requirement),
                "state": state,
                "treatment": treatment.model_dump(mode="json") if treatment else None,
            }
        )

    return {
        "applicable": applicable,
        "exempt_reason": "" if applicable else "public_demo",
        "requirements_total": len(requirements),
        "complete_count": state_counts.get("complete", 0),
        "incomplete_count": len(requirements) - state_counts.get("complete", 0),
        "state_counts": state_counts,
        "items": items,
        "evaluation_version_digest": current_digest,
    }
