# core/gates/risk_profile.py
"""Backward-compatible import surface for the risk model.

The implementation moved to :mod:`core.risk` in Milestone 2. Existing callers
and tests keep importing ``ProjectGateRiskTier`` / ``classify_project_risk`` /
``build_stage3_gate_profile`` from this module.
"""

from __future__ import annotations

from core.risk.assessment import classify_project_risk
from core.risk.models import ProjectGateRiskTier
from core.risk.profile import (
    Stage3GateProfile,
    build_stage3_gate_profile,
    requires_strict_structured_output,
)

__all__ = [
    "ProjectGateRiskTier",
    "Stage3GateProfile",
    "build_stage3_gate_profile",
    "classify_project_risk",
    "requires_strict_structured_output",
]
