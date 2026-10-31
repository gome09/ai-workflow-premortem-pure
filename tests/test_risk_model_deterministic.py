# tests/test_risk_model_deterministic.py
"""Milestone 2: deterministic six-factor risk model boundaries."""

from __future__ import annotations

import pytest

from core.models import ProjectContext
from core.risk.assessment import (
    RiskOverridePermissionError,
    apply_risk_override,
    assess_project_risk,
)
from core.risk.models import ProjectGateRiskTier, RiskFactorScores
from core.risk.profile import build_stage3_gate_profile, requires_strict_structured_output
from core.risk.rules import score_factors, tier_from_score


def _ctx(factors: RiskFactorScores, classification: str = "business_internal") -> ProjectContext:
    return ProjectContext(
        research_target="确定性风险模型测试",
        data_classification=classification,
        risk_profile=factors,
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, ProjectGateRiskTier.LOW),
        (4, ProjectGateRiskTier.LOW),
        (5, ProjectGateRiskTier.MEDIUM),
        (14, ProjectGateRiskTier.MEDIUM),
        (15, ProjectGateRiskTier.HIGH),
        (21, ProjectGateRiskTier.HIGH),
        (22, ProjectGateRiskTier.CRITICAL),
        (42, ProjectGateRiskTier.CRITICAL),
    ],
)
def test_score_band_boundaries(score: int, expected: ProjectGateRiskTier):
    assert tier_from_score(score) == expected


@pytest.mark.parametrize(
    ("factors", "expected"),
    [
        # score 0 → LOW
        (
            RiskFactorScores(
                impact=0,
                autonomy=0,
                data_sensitivity=0,
                reversibility=0,
                scale=0,
                external_exposure=0,
            ),
            ProjectGateRiskTier.LOW,
        ),
        # score 4 → LOW
        (
            RiskFactorScores(
                impact=0,
                autonomy=0,
                data_sensitivity=1,
                reversibility=1,
                scale=0,
                external_exposure=0,
            ),
            ProjectGateRiskTier.LOW,
        ),
        # score 5 → MEDIUM
        (
            RiskFactorScores(
                impact=1,
                autonomy=0,
                data_sensitivity=1,
                reversibility=0,
                scale=0,
                external_exposure=0,
            ),
            ProjectGateRiskTier.MEDIUM,
        ),
        # score 14 → MEDIUM
        (
            RiskFactorScores(
                impact=1,
                autonomy=1,
                data_sensitivity=1,
                reversibility=1,
                scale=1,
                external_exposure=1,
            ),
            ProjectGateRiskTier.MEDIUM,
        ),
        # score 18, no floor → HIGH
        (
            RiskFactorScores(
                impact=1,
                autonomy=2,
                data_sensitivity=1,
                reversibility=1,
                scale=1,
                external_exposure=1,
            ),
            ProjectGateRiskTier.HIGH,
        ),
        # score 21, floor HIGH → HIGH
        (
            RiskFactorScores(
                impact=2,
                autonomy=1,
                data_sensitivity=2,
                reversibility=2,
                scale=1,
                external_exposure=1,
            ),
            ProjectGateRiskTier.HIGH,
        ),
        # score 25, autonomy floor → CRITICAL
        (
            RiskFactorScores(
                impact=2,
                autonomy=2,
                data_sensitivity=2,
                reversibility=2,
                scale=1,
                external_exposure=1,
            ),
            ProjectGateRiskTier.CRITICAL,
        ),
        # severe impact floor → at least HIGH
        (
            RiskFactorScores(
                impact=3,
                autonomy=0,
                data_sensitivity=0,
                reversibility=0,
                scale=0,
                external_exposure=0,
            ),
            ProjectGateRiskTier.HIGH,
        ),
        # sensitive data + material impact floor → CRITICAL
        (
            RiskFactorScores(
                impact=2,
                autonomy=0,
                data_sensitivity=3,
                reversibility=0,
                scale=0,
                external_exposure=0,
            ),
            ProjectGateRiskTier.CRITICAL,
        ),
        # irreversible + material impact → CRITICAL
        (
            RiskFactorScores(
                impact=2,
                autonomy=0,
                data_sensitivity=1,
                reversibility=3,
                scale=1,
                external_exposure=1,
            ),
            ProjectGateRiskTier.CRITICAL,
        ),
    ],
)
def test_factor_matrix(factors: RiskFactorScores, expected: ProjectGateRiskTier):
    ctx = _ctx(factors)
    assessment = assess_project_risk(ctx)
    assert assessment.structural_tier == tier_from_score(score_factors(factors))
    assert assessment.effective_tier == expected


def test_sensitive_personal_floor_is_sticky_high():
    ctx = _ctx(
        RiskFactorScores(
            impact=0,
            autonomy=0,
            data_sensitivity=0,
            reversibility=0,
            scale=0,
            external_exposure=0,
        ),
        classification="sensitive_personal",
    )
    assert assess_project_risk(ctx).effective_tier == ProjectGateRiskTier.HIGH


def test_sensitive_personal_with_high_domain_factors_is_critical():
    ctx = _ctx(
        RiskFactorScores(
            impact=2,
            autonomy=1,
            data_sensitivity=2,
            reversibility=2,
            scale=1,
            external_exposure=1,
        ),
        classification="sensitive_personal",
    )
    assert assess_project_risk(ctx).effective_tier == ProjectGateRiskTier.CRITICAL
    assert requires_strict_structured_output(ctx) is True


def test_public_demo_stays_exempt_from_strict_structured_output():
    ctx = _ctx(
        RiskFactorScores(
            impact=3,
            autonomy=2,
            data_sensitivity=3,
            reversibility=2,
            scale=2,
            external_exposure=1,
        ),
        classification="public_demo",
    )
    assert assess_project_risk(ctx).effective_tier == ProjectGateRiskTier.CRITICAL
    assert requires_strict_structured_output(ctx) is False
    assert build_stage3_gate_profile(ctx).require_expert_review is True


def test_same_input_produces_identical_tier_and_reasons():
    factors = RiskFactorScores(
        impact=2,
        autonomy=1,
        data_sensitivity=2,
        reversibility=2,
        scale=1,
        external_exposure=1,
    )
    ctx = _ctx(factors)
    results = [assess_project_risk(ctx) for _ in range(20)]
    assert {result.effective_tier for result in results} == {ProjectGateRiskTier.HIGH}
    first = results[0]
    assert all(result.reasons == first.reasons for result in results)


def test_override_upgrade_is_recorded_and_audited():
    ctx = _ctx(
        RiskFactorScores(
            impact=0,
            autonomy=0,
            data_sensitivity=0,
            reversibility=0,
            scale=0,
            external_exposure=0,
        )
    )
    record = apply_risk_override(
        ctx,
        requested_tier="high",
        reason="业务方确认对外发布",
        actor="alice",
        actor_role="editor",
    )
    assessment = assess_project_risk(ctx)
    assert assessment.effective_tier == ProjectGateRiskTier.HIGH
    assert record.original_tier == "low"
    assert record.effective_tier == "high"
    assert any(e.event_type == "risk_tier_overridden" for e in ctx.audit_events)


def test_override_downgrade_requires_admin():
    ctx = _ctx(
        RiskFactorScores(
            impact=1,
            autonomy=2,
            data_sensitivity=1,
            reversibility=1,
            scale=1,
            external_exposure=1,
        )
    )
    assert assess_project_risk(ctx).effective_tier == ProjectGateRiskTier.HIGH
    with pytest.raises(RiskOverridePermissionError):
        apply_risk_override(
            ctx,
            requested_tier="medium",
            reason="误判",
            actor="bob",
            actor_role="editor",
        )


def test_override_downgrade_clamped_by_floor():
    ctx = _ctx(
        RiskFactorScores(
            impact=1,
            autonomy=2,
            data_sensitivity=1,
            reversibility=1,
            scale=1,
            external_exposure=1,
        )
    )
    record = apply_risk_override(
        ctx,
        requested_tier="medium",
        reason="管理员复核后下调",
        actor="admin",
        actor_role="admin",
    )
    assert record.requested_tier == "medium"
    assert record.effective_tier == "medium"
    assert assess_project_risk(ctx).effective_tier == ProjectGateRiskTier.MEDIUM


def test_override_below_floor_is_clamped_and_transparent():
    ctx = _ctx(
        RiskFactorScores(
            impact=0,
            autonomy=0,
            data_sensitivity=0,
            reversibility=0,
            scale=0,
            external_exposure=0,
        ),
        classification="sensitive_personal",
    )
    assert assess_project_risk(ctx).effective_tier == ProjectGateRiskTier.HIGH
    record = apply_risk_override(
        ctx,
        requested_tier="low",
        reason="数据已脱敏",
        actor="admin",
        actor_role="admin",
    )
    assert record.requested_tier == "low"
    assert record.floor_tier == "high"
    assert record.effective_tier == "high"
    assert assess_project_risk(ctx).effective_tier == ProjectGateRiskTier.HIGH
