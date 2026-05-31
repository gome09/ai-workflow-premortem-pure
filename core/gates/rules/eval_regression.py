# core/gates/rules/eval_regression.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.eval_regression_policy import build_stage_regression_decisions
from core.gates.risk_profile import build_stage3_gate_profile
from core.models import ProjectContext


class EvalRegressionRule:
    """Direct GateRule: block Stage 3 advancement on EvalExperiment regression.

    v0.8.0-alpha.2 deliberately keeps this rule pure-read. It consumes existing
    EvalDataset / EvalExperiment / comparison_summary records but never creates,
    runs, or compares experiments during gate evaluation.

    v0.8.0-beta.2: risk-adaptive — low-risk projects skip regression blocking
    unless the dataset has metadata.gate_required=true.
    """

    rule_id = "eval_regression"
    applies_to_stages = {3}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 3:
            return []

        profile = build_stage3_gate_profile(ctx)

        # Build dataset lookup for gate_required check
        dataset_by_id = {ds.dataset_id: ds for ds in getattr(ctx, "eval_datasets", []) or []}

        blockers: list[readiness.StageBlocker] = []
        for decision in build_stage_regression_decisions(ctx, stage=stage):
            if not decision.blocking:
                continue

            # Risk-adaptive: for low/medium risk, only block on datasets
            # that explicitly require gate enforcement.
            if not profile.require_eval_regression:
                dataset = dataset_by_id.get(decision.dataset_id)
                dataset_gate_required = bool(
                    dataset and (dataset.metadata or {}).get("gate_required")
                )
                if not dataset_gate_required:
                    continue

            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="eval_regression",
                    severity=decision.severity,  # type: ignore[arg-type]
                    message=decision.message,
                    source_type=decision.source_type,
                    source_id=decision.source_id or decision.dataset_id,
                    required_resolution=decision.required_resolution,  # type: ignore[arg-type]
                    can_be_overridden_by_approval=False,
                    metadata={
                        **decision.metadata,
                        "decision_status": decision.status,
                        "dataset_id": decision.dataset_id,
                        "experiment_id": decision.experiment_id,
                        "baseline_experiment_id": decision.baseline_experiment_id,
                        "gate_rule_id": self.rule_id,
                    },
                )
            )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = EvalRegressionRule()
