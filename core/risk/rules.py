# core/risk/rules.py
"""Deterministic aggregation of six risk factors into a project risk tier.

The rules here are pure: no persistence, no LLM, no gate imports. This is the
single source of truth for LOW/MEDIUM/HIGH/CRITICAL derivation.
"""

from __future__ import annotations

from core.risk.models import (
    TIER_ORDER,
    ProjectGateRiskTier,
    RiskEvaluation,
    RiskFactorScores,
)

FACTOR_WEIGHTS: dict[str, int] = {
    "impact": 3,
    "autonomy": 4,
    "data_sensitivity": 2,
    "reversibility": 2,
    "scale": 1,
    "external_exposure": 2,
}

# Inclusive score bands. CRITICAL starts at 22, so the full 0-42 range is
# covered without gaps.
SCORE_BANDS: tuple[tuple[int, ProjectGateRiskTier], ...] = (
    (4, ProjectGateRiskTier.LOW),
    (14, ProjectGateRiskTier.MEDIUM),
    (21, ProjectGateRiskTier.HIGH),
    (42, ProjectGateRiskTier.CRITICAL),
)


def _max_tier(*tiers: ProjectGateRiskTier) -> ProjectGateRiskTier:
    return max(tiers, key=lambda tier: TIER_ORDER[tier])


def score_factors(factors: RiskFactorScores) -> int:
    """Return the weighted deterministic score for *factors*."""
    values = factors.as_dict()
    return sum(FACTOR_WEIGHTS[name] * value for name, value in values.items())


def tier_from_score(score: int) -> ProjectGateRiskTier:
    """Map a weighted score to a structural tier using fixed inclusive bands."""
    for upper, tier in SCORE_BANDS:
        if score <= upper:
            return tier
    return ProjectGateRiskTier.CRITICAL


def _collect_floor(
    factors: RiskFactorScores,
    structural_tier: ProjectGateRiskTier,
    data_classification: str,
) -> tuple[ProjectGateRiskTier, list[str]]:
    """Return the maximum hard floor and its deterministic reason list."""
    floor = ProjectGateRiskTier.LOW
    reasons: list[str] = []

    def _raise(tier: ProjectGateRiskTier, reason: str) -> None:
        nonlocal floor
        floor = _max_tier(floor, tier)
        reasons.append(reason)

    if data_classification == "sensitive_personal":
        _raise(
            ProjectGateRiskTier.HIGH,
            "floor: sensitive_personal classification requires at least HIGH",
        )
        if structural_tier in {ProjectGateRiskTier.HIGH, ProjectGateRiskTier.CRITICAL}:
            _raise(
                ProjectGateRiskTier.CRITICAL,
                "floor: sensitive_personal combined with high structural risk requires CRITICAL",
            )
        if factors.impact >= 2 and factors.reversibility >= 2:
            _raise(
                ProjectGateRiskTier.CRITICAL,
                "floor: sensitive_personal with material impact and hard-to-reverse action requires CRITICAL",
            )

    if factors.impact == 3 and (
        factors.autonomy >= 2 or factors.reversibility >= 2 or factors.external_exposure >= 2
    ):
        _raise(
            ProjectGateRiskTier.CRITICAL,
            "floor: severe impact combined with autonomy/reversibility/external exposure requires CRITICAL",
        )

    if factors.data_sensitivity == 3 and factors.impact >= 2:
        _raise(
            ProjectGateRiskTier.CRITICAL,
            "floor: highly sensitive data combined with material impact requires CRITICAL",
        )

    if factors.autonomy >= 2 and factors.data_sensitivity >= 3 and factors.impact >= 2:
        _raise(
            ProjectGateRiskTier.CRITICAL,
            "floor: autonomous action over highly sensitive data requires CRITICAL",
        )

    if factors.reversibility == 3 and factors.impact >= 2:
        _raise(
            ProjectGateRiskTier.CRITICAL,
            "floor: irreversible action with material impact requires CRITICAL",
        )

    if factors.external_exposure == 3 and (factors.autonomy >= 2 or factors.data_sensitivity >= 2):
        _raise(
            ProjectGateRiskTier.CRITICAL,
            "floor: public/external exposure with autonomy or sensitive data requires CRITICAL",
        )

    if factors.impact == 3:
        _raise(
            ProjectGateRiskTier.HIGH,
            "floor: severe impact requires at least HIGH",
        )

    if factors.impact >= 2 and factors.autonomy >= 2:
        _raise(
            ProjectGateRiskTier.HIGH,
            "floor: material impact with autonomous execution requires at least HIGH",
        )

    if factors.impact >= 2 and factors.external_exposure >= 2:
        _raise(
            ProjectGateRiskTier.HIGH,
            "floor: material impact with external exposure requires at least HIGH",
        )

    if factors.data_sensitivity >= 3:
        _raise(
            ProjectGateRiskTier.HIGH,
            "floor: highly sensitive data requires at least HIGH",
        )

    if factors.scale == 3 and factors.data_sensitivity >= 2:
        _raise(
            ProjectGateRiskTier.HIGH,
            "floor: public/multi-tenant scale with sensitive data requires at least HIGH",
        )

    if factors.reversibility >= 2 and factors.impact >= 2:
        _raise(
            ProjectGateRiskTier.HIGH,
            "floor: hard-to-reverse action with material impact requires at least HIGH",
        )

    return floor, reasons


def evaluate_risk(
    factors: RiskFactorScores,
    *,
    data_classification: str = "business_internal",
) -> RiskEvaluation:
    """Evaluate *factors* deterministically and return structural/floor/effective tiers."""
    score = score_factors(factors)
    structural_tier = tier_from_score(score)
    floor_tier, floor_reasons = _collect_floor(factors, structural_tier, data_classification)
    effective_tier = _max_tier(structural_tier, floor_tier)
    reasons = [
        f"score={score}; structural_tier={structural_tier.value}",
        *floor_reasons,
        f"effective_tier={effective_tier.value}",
    ]
    return RiskEvaluation(
        structural_tier=structural_tier,
        floor_tier=floor_tier,
        effective_tier=effective_tier,
        score=score,
        reasons=reasons,
    )
