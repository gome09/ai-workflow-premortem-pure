# core/risk/models.py
"""Structured risk model primitives.

This module intentionally does not import ``core.models``. ``ProjectContext``
imports these models, so importing back would create an import cycle.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from core.ids import new_id

RiskTier = Literal["low", "medium", "high", "critical"]
RiskFactorSource = Literal[
    "human",
    "scenario",
    "llm_assisted",
    "system_default",
    "legacy_inference",
]


class ProjectGateRiskTier(StrEnum):
    """Canonical project risk tier used by gates and coverage policy.

    Kept at this location (rather than ``core.gates.risk_profile``) so the
    structured risk model has no dependency on the gate package. The gate
    module re-exports this enum for backward-compatible imports.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


TIER_ORDER: dict[ProjectGateRiskTier, int] = {
    ProjectGateRiskTier.LOW: 0,
    ProjectGateRiskTier.MEDIUM: 1,
    ProjectGateRiskTier.HIGH: 2,
    ProjectGateRiskTier.CRITICAL: 3,
}


class RiskFactorScores(BaseModel):
    """Six deterministic risk factors, each on a 0-3 ordinal scale.

    0 = absent / negligible, 1 = limited, 2 = elevated, 3 = severe.
    """

    impact: int = Field(default=1, ge=0, le=3)
    autonomy: int = Field(default=1, ge=0, le=3)
    data_sensitivity: int = Field(default=1, ge=0, le=3)
    reversibility: int = Field(default=1, ge=0, le=3)
    scale: int = Field(default=1, ge=0, le=3)
    external_exposure: int = Field(default=1, ge=0, le=3)
    rationale: str = ""
    source: RiskFactorSource = "system_default"

    def as_dict(self) -> dict[str, int]:
        return {
            "impact": self.impact,
            "autonomy": self.autonomy,
            "data_sensitivity": self.data_sensitivity,
            "reversibility": self.reversibility,
            "scale": self.scale,
            "external_exposure": self.external_exposure,
        }


class RiskOverrideRecord(BaseModel):
    """Append-only human override record for project risk tier."""

    override_id: str = Field(default_factory=lambda: new_id("RISK-"))
    session_id: str
    tenant_id: str = ""
    actor: str = "user"
    actor_role: str = ""
    original_tier: RiskTier
    requested_tier: RiskTier
    effective_tier: RiskTier
    floor_tier: RiskTier
    reason: str = ""
    # 版本绑定：记录 override 生效时的风险输入摘要。风险因子或数据分级变化后，
    # 摘要不匹配的 override 不再生效（旧记录该字段为空，按兼容语义继续生效）。
    factors_digest: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RiskAssessment(BaseModel):
    """Deterministic risk assessment result.

    ``effective_tier`` is what gate profile and strict-output policy consume.
    ``llm_explanation`` is explanatory only and must never influence the tier.
    """

    factors: RiskFactorScores
    structural_tier: ProjectGateRiskTier
    floor_tier: ProjectGateRiskTier
    effective_tier: ProjectGateRiskTier
    reasons: list[str] = Field(default_factory=list)
    source: RiskFactorSource = "system_default"
    override_id: str | None = None
    llm_explanation: str = ""


class RiskEvaluation(BaseModel):
    """Pure deterministic evaluation of factors (without override resolution)."""

    structural_tier: ProjectGateRiskTier
    floor_tier: ProjectGateRiskTier
    effective_tier: ProjectGateRiskTier
    score: int
    reasons: list[str] = Field(default_factory=list)
