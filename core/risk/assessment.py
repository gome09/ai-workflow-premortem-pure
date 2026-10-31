# core/risk/assessment.py
"""Risk assessment resolution, human override, and compatibility wrappers."""

from __future__ import annotations

from typing import Any

from core.audit_service import append_audit_event
from core.models import ProjectContext
from core.risk.inference import infer_legacy_factors
from core.risk.models import (
    TIER_ORDER,
    ProjectGateRiskTier,
    RiskAssessment,
    RiskFactorScores,
    RiskOverrideRecord,
)
from core.risk.rules import evaluate_risk


class RiskOverridePermissionError(PermissionError):
    """Raised when a non-admin attempts to downgrade the project risk tier."""


def _tier(value: str) -> ProjectGateRiskTier:
    try:
        return ProjectGateRiskTier(str(value).lower())
    except ValueError as exc:
        allowed = sorted(tier.value for tier in ProjectGateRiskTier)
        raise ValueError(f"Unknown risk tier {value!r}; allowed: {allowed}") from exc


def _max_tier(*tiers: ProjectGateRiskTier) -> ProjectGateRiskTier:
    return max(tiers, key=lambda tier: TIER_ORDER[tier])


def resolve_factors(ctx: ProjectContext) -> tuple[RiskFactorScores, list[str]]:
    """Resolve the structured factor input for *ctx* deterministically."""
    if ctx.risk_profile is not None:
        source = ctx.risk_profile.source
        reasons = [f"source: explicit risk_profile (source={source})"]
        if ctx.risk_profile.rationale:
            reasons.append(f"rationale: {ctx.risk_profile.rationale}")
        return ctx.risk_profile, reasons

    scenario_profile = (ctx.scenario_config or {}).get("risk_profile")
    if isinstance(scenario_profile, dict):
        try:
            factors = RiskFactorScores.model_validate({**scenario_profile, "source": "scenario"})
        except Exception:
            # Invalid scenario manifests must not break session creation; fall
            # back to deterministic inference and keep the warning in reasons.
            factors, reasons = infer_legacy_factors(ctx)
            return factors, [*reasons, "warning: invalid scenario risk_profile ignored"]
        return factors, ["source: explicit risk_profile (source=scenario)"]

    return infer_legacy_factors(ctx)


def _latest_override(ctx: ProjectContext) -> RiskOverrideRecord | None:
    overrides = list(getattr(ctx, "risk_overrides", []) or [])
    return overrides[-1] if overrides else None


def assess_project_risk(ctx: ProjectContext) -> RiskAssessment:
    """Return the deterministic assessment consumed by gates and reports."""
    factors, source_reasons = resolve_factors(ctx)
    evaluation = evaluate_risk(factors, data_classification=ctx.data_classification)

    reasons = [
        *source_reasons,
        (
            "factor:"
            f"impact={factors.impact},"
            f"autonomy={factors.autonomy},"
            f"data_sensitivity={factors.data_sensitivity},"
            f"reversibility={factors.reversibility},"
            f"scale={factors.scale},"
            f"external_exposure={factors.external_exposure}"
        ),
        *evaluation.reasons,
    ]

    override = _latest_override(ctx)
    if override is not None:
        effective = _max_tier(_tier(override.requested_tier), evaluation.floor_tier)
        reasons.append(
            "override: "
            f"{override.override_id} requested={override.requested_tier} "
            f"effective={effective.value} floor={evaluation.floor_tier.value} "
            f"actor={override.actor} role={override.actor_role}"
        )
    else:
        effective = evaluation.effective_tier

    llm_explanation = ""
    if ctx.stage_1_output is not None:
        llm_explanation = ctx.stage_1_output.direct_conclusion or ""

    return RiskAssessment(
        factors=factors,
        structural_tier=evaluation.structural_tier,
        floor_tier=evaluation.floor_tier,
        effective_tier=effective,
        reasons=reasons,
        source=factors.source,
        override_id=override.override_id if override else None,
        llm_explanation=llm_explanation,
    )


def classify_project_risk(ctx: ProjectContext) -> tuple[ProjectGateRiskTier, list[str]]:
    """Backward-compatible ``(tier, reasons)`` contract."""
    assessment = assess_project_risk(ctx)
    return assessment.effective_tier, assessment.reasons


def set_risk_profile(
    ctx: ProjectContext,
    factors: RiskFactorScores,
    *,
    actor: str = "user",
    actor_role: str = "",
    note: str = "",
) -> RiskAssessment:
    """Persist explicit factor scores on the context and write an audit event."""
    before = assess_project_risk(ctx)
    updated = factors.model_copy(update={"source": "human"})
    ctx.risk_profile = updated
    append_audit_event(
        ctx,
        actor="user",
        event_type="risk_profile_updated",
        target_type="session",
        target_id=ctx.session_id,
        before={
            "factors": before.factors.as_dict(),
            "effective_tier": before.effective_tier.value,
        },
        after={
            "factors": updated.as_dict(),
            "effective_tier": assess_project_risk(ctx).effective_tier.value,
        },
        metadata={
            "actor": actor,
            "actor_role": actor_role,
            "tenant_id": ctx.tenant_id,
            "note": note,
            "rationale": updated.rationale,
        },
    )
    return assess_project_risk(ctx)


def apply_risk_override(
    ctx: ProjectContext,
    *,
    requested_tier: str,
    reason: str,
    actor: str = "user",
    actor_role: str = "",
) -> RiskOverrideRecord:
    """Record a human override, clamped to the deterministic floor."""
    requested = _tier(requested_tier)
    normalized_reason = (reason or "").strip()
    if not normalized_reason:
        raise ValueError("Risk override reason is required")

    current = assess_project_risk(ctx)
    if TIER_ORDER[requested] < TIER_ORDER[current.effective_tier] and actor_role != "admin":
        raise RiskOverridePermissionError("Downgrading project risk tier requires admin role")

    effective = _max_tier(requested, current.floor_tier)
    record = RiskOverrideRecord(
        session_id=ctx.session_id,
        tenant_id=ctx.tenant_id,
        actor=actor,
        actor_role=actor_role,
        original_tier=current.effective_tier.value,
        requested_tier=requested.value,
        effective_tier=effective.value,
        floor_tier=current.floor_tier.value,
        reason=normalized_reason,
    )
    ctx.risk_overrides.append(record)

    append_audit_event(
        ctx,
        actor="user",
        event_type="risk_tier_overridden",
        target_type="session",
        target_id=ctx.session_id,
        before={"risk_tier": current.effective_tier.value, "override_id": None},
        after={"risk_tier": effective.value, "override_id": record.override_id},
        metadata={
            "override_id": record.override_id,
            "original_tier": record.original_tier,
            "requested_tier": record.requested_tier,
            "effective_tier": record.effective_tier,
            "floor_tier": record.floor_tier,
            "reason": normalized_reason,
            "actor": actor,
            "actor_role": actor_role,
            "tenant_id": ctx.tenant_id,
            "clamped_by_floor": requested != effective,
        },
    )
    return record


def risk_profile_response(ctx: ProjectContext) -> dict[str, Any]:
    """Serializable payload for the risk-profile API/UI."""
    assessment = assess_project_risk(ctx)
    overrides = [
        record.model_dump(mode="json") for record in getattr(ctx, "risk_overrides", []) or []
    ]
    return {
        "session_id": ctx.session_id,
        "factors": assessment.factors.as_dict(),
        "structural_tier": assessment.structural_tier.value,
        "floor_tier": assessment.floor_tier.value,
        "effective_tier": assessment.effective_tier.value,
        "reasons": assessment.reasons,
        "source": assessment.source,
        "llm_explanation": assessment.llm_explanation,
        "override": overrides[-1] if overrides else None,
        "overrides": overrides,
    }
