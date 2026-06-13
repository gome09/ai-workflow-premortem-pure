from __future__ import annotations

import core.stage_readiness_service as readiness
from core.gates.risk_profile import build_stage3_gate_profile
from core.models import ProjectContext
from core.trace_backfill_service import build_trace_backfill_summary


class TraceBackfillGapRule:
    """Stage 3 trace-backfill gate for v0.8.0-alpha.8.

    The rule is pure-read. It consumes existing LLMTrace, EvalCase, and
    EvalDataset records and only explains the next required operation.
    It never creates EvalCases or datasets during gate evaluation.

    v0.8.0-beta.2: risk-adaptive — low-risk projects skip trace backfill
    blocking.
    """

    rule_id = "trace_backfill_gap"
    applies_to_stages = {3}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 3:
            return []

        profile = build_stage3_gate_profile(ctx)

        if not profile.require_trace_backfill:
            return []

        summary = build_trace_backfill_summary(ctx)
        blockers: list[readiness.StageBlocker] = []

        for trace_id in summary.get("eligible_trace_ids_without_eval_case", []) or []:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="trace_backfill_gap",
                    severity="high",
                    message=f"Failed/parser/safety trace {trace_id} has not been backfilled into an EvalCase.",
                    source_type="trace",
                    source_id=trace_id,
                    required_resolution="trace_to_eval_case",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "trace_without_eval_case", **summary},
                )
            )

        for eval_id in summary.get("backfilled_eval_ids_without_trace_dataset", []) or []:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="trace_backfill_gap",
                    severity="high",
                    message=f"Trace-backfilled EvalCase {eval_id} is not included in a production_trace EvalDataset.",
                    source_type="eval_case",
                    source_id=eval_id,
                    required_resolution="create_trace_backfill_dataset",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "trace_eval_case_without_dataset", **summary},
                )
            )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = TraceBackfillGapRule()
