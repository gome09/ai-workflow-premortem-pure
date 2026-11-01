# core/gates/rules/risk_treatment.py
"""Stage 4 gate: high/critical risks need an accountable, reviewed treatment.

public_demo sessions are exempt, consistent with the existing demo isolation
policy. The rule is read-only: treatment records are created through the risk
treatment API, not by mutating context during gate evaluation.
"""

from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import ProjectContext
from core.risk_treatment_service import treatment_blockers


class RiskTreatmentRule:
    """Direct GateRule: every high/critical item has a reviewed treatment."""

    rule_id = "risk_treatment"
    applies_to_stages = {4}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 4:
            return []

        blockers: list[readiness.StageBlocker] = []
        for item in treatment_blockers(ctx):
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=4,
                    blocker_type="risk_treatment",
                    severity=item["risk_level"],
                    message=item["message"],
                    source_type=item["source_type"],
                    source_id=item["source_id"],
                    action_id=None,
                    required_resolution="complete_risk_treatment",
                    can_be_overridden_by_approval=False,
                    metadata={
                        "gap_type": item["gap_type"],
                        "treatment_id": item["treatment_id"],
                        "required_resolution": item["required_resolution"],
                        "api_path_template": "/sessions/{session_id}/risk-treatments",
                    },
                )
            )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = RiskTreatmentRule()
