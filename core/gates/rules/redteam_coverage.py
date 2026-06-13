# core/gates/rules/redteam_coverage.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.gates.risk_profile import build_stage3_gate_profile
from core.models import ProjectContext
from core.redteam_service import build_redteam_coverage_summary


class RedTeamCoverageRule:
    """Stage 3 Red Team coverage gate.

    The rule is pure-read: it only explains missing RedTeamCase coverage,
    approval, EvalCase sync, and redteam_generated dataset linkage.

    Risk-adaptive: low/medium-risk projects are not blocked by missing redteam
    coverage unless there are actual high/critical safety findings or adversarial
    critical cases.
    """

    rule_id = "redteam_coverage"
    applies_to_stages = {3}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 3:
            return []

        profile = build_stage3_gate_profile(ctx)

        summary = build_redteam_coverage_summary(ctx, stage=stage)

        # Risk-adaptive: for low/medium risk projects, only block if there
        # are actual high/critical safety findings that lack redteam coverage.
        if not profile.require_redteam_coverage:
            # Still block if there are missing safety finding redteam cases
            # (these indicate real safety gaps, not just missing coverage).
            has_safety_gaps = bool(summary.get("missing_safety_finding_ids"))
            if not has_safety_gaps:
                return []

        blockers: list[readiness.StageBlocker] = []

        for finding_id in summary.get("missing_safety_finding_ids", []) or []:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="redteam_coverage",
                    severity="high",
                    message=f"高风险 SafetyFinding {finding_id} 缺少 RedTeamCase 覆盖。",
                    source_type="safety_finding",
                    source_id=finding_id,
                    required_resolution="generate_redteam_cases",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "missing_safety_redteam_case", **summary},
                )
            )

        for node_id in summary.get("missing_node_ids", []) or []:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="redteam_coverage",
                    severity="high",
                    message=f"高风险工作流节点 {node_id} 缺少 RedTeamCase 覆盖。",
                    source_type="workflow_node",
                    source_id=node_id,
                    required_resolution="generate_redteam_cases",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "missing_node_redteam_case", **summary},
                )
            )

        for case_id in summary.get("draft_high_case_ids", []) or []:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="redteam_coverage",
                    severity="high",
                    message=f"高风险 RedTeamCase {case_id} 仍为 draft，需人工批准后才能进入 Eval。",
                    source_type="redteam_case",
                    source_id=case_id,
                    required_resolution="approve_redteam_case",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "draft_redteam_case", **summary},
                )
            )

        for case_id in summary.get("approved_unsynced_case_ids", []) or []:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="redteam_coverage",
                    severity="high",
                    message=f"已批准 RedTeamCase {case_id} 尚未同步为 EvalCase。",
                    source_type="redteam_case",
                    source_id=case_id,
                    required_resolution="sync_redteam_eval_case",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "approved_redteam_case_not_synced", **summary},
                )
            )

        for case_id in summary.get("missing_linked_eval_case_ids", []) or []:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="redteam_coverage",
                    severity="high",
                    message=f"RedTeamCase {case_id} 标记为已同步，但 linked EvalCase 不存在。",
                    source_type="redteam_case",
                    source_id=case_id,
                    required_resolution="sync_redteam_eval_case",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "linked_eval_case_missing", **summary},
                )
            )

        for eval_id in summary.get("synced_eval_ids_without_redteam_dataset", []) or []:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="redteam_coverage",
                    severity="high",
                    message=f"RedTeam EvalCase {eval_id} 尚未进入 redteam_generated EvalDataset。",
                    source_type="eval_case",
                    source_id=eval_id,
                    required_resolution="create_redteam_dataset",
                    can_be_overridden_by_approval=False,
                    metadata={"gap_type": "redteam_eval_case_not_in_dataset", **summary},
                )
            )

        # For low/medium risk, only keep safety-finding-related blockers.
        # Node coverage, draft cases, sync gaps, and dataset gaps are advisory.
        if not profile.require_redteam_coverage:
            blockers = [
                b for b in blockers if b.metadata.get("gap_type") == "missing_safety_redteam_case"
            ]

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = RedTeamCoverageRule()
