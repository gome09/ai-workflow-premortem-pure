# core/risk/assessment.py
"""Risk assessment resolution, human override, and compatibility wrappers."""

from __future__ import annotations

import hashlib
import json
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


def _digest_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def risk_factor_digest_for(factors: RiskFactorScores, data_classification: str) -> str:
    """Digest of the deterministic risk inputs (without any human override)."""
    evaluation = evaluate_risk(factors, data_classification=data_classification)
    return _digest_payload(
        {
            "factors": factors.as_dict(),
            "data_classification": data_classification,
            "structural_tier": evaluation.structural_tier.value,
            "floor_tier": evaluation.floor_tier.value,
        }
    )


def risk_factor_digest(ctx: ProjectContext) -> str:
    factors, _ = resolve_factors(ctx)
    return risk_factor_digest_for(factors, ctx.data_classification)


def risk_assessment_digest(ctx: ProjectContext) -> str:
    """Digest binding an approval to one concrete risk assessment state.

    Used by the CRITICAL expert-review gate so that approvals issued for an
    older factor set / override cannot unblock a changed risk profile.
    """
    assessment = assess_project_risk(ctx)
    return _digest_payload(
        {
            "factor_digest": risk_factor_digest_for(assessment.factors, ctx.data_classification),
            "effective_tier": assessment.effective_tier.value,
            "override_id": assessment.override_id,
        }
    )


def _assert_tier_downgrade_allowed(
    actor_role: str,
    before_tier: ProjectGateRiskTier,
    after_tier: ProjectGateRiskTier,
) -> None:
    """Shared downgrade guard for every entry point that can change the tier."""
    if TIER_ORDER[after_tier] < TIER_ORDER[before_tier] and actor_role != "admin":
        raise RiskOverridePermissionError("Downgrading project risk tier requires admin role")


def _build_assessment(
    ctx: ProjectContext,
    factors: RiskFactorScores,
    source_reasons: list[str],
) -> RiskAssessment:
    """Build an assessment from explicit factors without mutating *ctx*."""
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
    if override is not None and override.factors_digest:
        current_digest = risk_factor_digest_for(factors, ctx.data_classification)
        if override.factors_digest != current_digest:
            reasons.append(
                f"override: {override.override_id} invalidated because risk inputs changed"
            )
            override = None

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


def assess_project_risk(ctx: ProjectContext) -> RiskAssessment:
    """Return the deterministic assessment consumed by gates and reports."""
    factors, source_reasons = resolve_factors(ctx)
    return _build_assessment(ctx, factors, source_reasons)


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
    """Persist explicit factor scores on the context and write an audit event.

    Any change that lowers the effective tier is treated exactly like a risk
    override downgrade: it requires the admin role, so editors cannot bypass
    the override permission by editing the six factors directly.
    """
    before = assess_project_risk(ctx)
    updated = factors.model_copy(update={"source": "human"})
    after = _build_assessment(
        ctx,
        updated,
        [f"source: explicit risk_profile (source={updated.source})"],
    )
    _assert_tier_downgrade_allowed(actor_role, before.effective_tier, after.effective_tier)
    is_downgrade = TIER_ORDER[after.effective_tier] < TIER_ORDER[before.effective_tier]

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
            "effective_tier": after.effective_tier.value,
        },
        metadata={
            "actor": actor,
            "actor_role": actor_role,
            "tenant_id": ctx.tenant_id,
            "note": note,
            "rationale": updated.rationale,
            "before_effective_tier": before.effective_tier.value,
            "after_effective_tier": after.effective_tier.value,
            "is_downgrade": is_downgrade,
            "downgrade_authorized_by": "admin" if is_downgrade else "",
            "factors_digest": risk_factor_digest_for(updated, ctx.data_classification),
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
    _assert_tier_downgrade_allowed(actor_role, current.effective_tier, requested)

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
        factors_digest=risk_factor_digest(ctx),
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
            "factors_digest": record.factors_digest,
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
