# core/gates/models.py
from __future__ import annotations

# Re-export the existing public models during the v0.7 compatibility migration.
from core.stage_readiness_service import StageBlocker, StageGateResult, StageReadiness

__all__ = ["StageBlocker", "StageGateResult", "StageReadiness"]
