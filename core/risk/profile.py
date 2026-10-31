# core/risk/profile.py
"""Risk-adaptive Stage 3 gate profile and strict-output policy."""

from __future__ import annotations

from dataclasses import dataclass

from core.models import ProjectContext
from core.risk.assessment import assess_project_risk
from core.risk.models import ProjectGateRiskTier


@dataclass(frozen=True)
class Stage3GateProfile:
    """Which advanced Stage 3 gate rules are blocking for this project."""

    risk_tier: ProjectGateRiskTier
    require_eval_coverage: bool
    require_failed_eval_resolution: bool
    require_redteam_coverage: bool
    require_eval_regression: bool
    require_trace_backfill: bool
    require_expert_review: bool
    rationale: str


def requires_strict_structured_output(ctx: ProjectContext) -> bool:
    """HIGH/CRITICAL projects must not accept weak stage-output fallbacks.

    Markdown fallbacks are lossy and inferred oversight policies are defaults
    rather than explicit supervision decisions. For high-risk projects both are
    treated as unsafe, so downstream parsing must keep parser errors and refuse
    to synthesize a policy. Public demo sessions stay exempt to keep the
    zero-configuration demo scenarios runnable.
    """
    if getattr(ctx, "data_classification", None) == "public_demo":
        return False
    assessment = assess_project_risk(ctx)
    if assessment.effective_tier in {
        ProjectGateRiskTier.HIGH,
        ProjectGateRiskTier.CRITICAL,
    }:
        return True
    return getattr(ctx, "data_classification", None) == "sensitive_personal"


def build_stage3_gate_profile(ctx: ProjectContext) -> Stage3GateProfile:
    """Build the Stage 3 gate profile from the deterministic risk assessment."""
    assessment = assess_project_risk(ctx)
    tier = assessment.effective_tier
    rationale = "; ".join(assessment.reasons)

    if tier == ProjectGateRiskTier.CRITICAL:
        return Stage3GateProfile(
            risk_tier=tier,
            require_eval_coverage=True,
            require_failed_eval_resolution=True,
            require_redteam_coverage=True,
            require_eval_regression=True,
            require_trace_backfill=True,
            require_expert_review=True,
            rationale=f"Critical-risk project. {rationale}",
        )

    if tier == ProjectGateRiskTier.HIGH:
        return Stage3GateProfile(
            risk_tier=tier,
            require_eval_coverage=True,
            require_failed_eval_resolution=True,
            require_redteam_coverage=True,
            require_eval_regression=True,
            require_trace_backfill=True,
            require_expert_review=False,
            rationale=f"High-risk project. {rationale}",
        )

    if tier == ProjectGateRiskTier.MEDIUM:
        return Stage3GateProfile(
            risk_tier=tier,
            require_eval_coverage=True,
            require_failed_eval_resolution=True,
            require_redteam_coverage=False,
            require_eval_regression=False,
            require_trace_backfill=False,
            require_expert_review=False,
            rationale=f"Medium-risk project. {rationale}",
        )

    return Stage3GateProfile(
        risk_tier=tier,
        require_eval_coverage=True,
        require_failed_eval_resolution=True,
        require_redteam_coverage=False,
        require_eval_regression=False,
        require_trace_backfill=False,
        require_expert_review=False,
        rationale=f"Low-risk project. {rationale}",
    )
