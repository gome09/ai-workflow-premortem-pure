# core/gates/rules/expert_review.py
"""Expert review gate rule — consumes Stage3GateProfile.require_expert_review.

补历史欠账：CRITICAL 档 require_expert_review=True 此前无规则消费
（见 stage3-risk-adaptive-gate.md "not implemented" 脚注）。
本规则在 Stage 3 评估时，若 profile.require_expert_review 且尚无 approved
专家复核动作，则产出阻断 blocker（action_type=escalate）。
"""

from __future__ import annotations

import uuid

import core.stage_readiness_service as readiness
from core.gates.risk_profile import build_stage3_gate_profile
from core.models import PendingHumanAction, ProjectContext


class ExpertReviewRule:
    """Stage 3 expert-review enforcement for CRITICAL-risk projects."""

    rule_id = "expert_review"
    applies_to_stages = {3}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 3:
            return []

        profile = build_stage3_gate_profile(ctx)
        if not profile.require_expert_review:
            return []

        current_version = readiness._current_version(ctx, stage)
        existing = [
            a
            for a in ctx.pending_actions
            if a.source_type == "expert_review"
            and a.stage_id == stage
            and a.stage_output_version == current_version
            and a.status in {"pending", "resolved"}
        ]
        # 已批准 → 不阻断
        if any(a.status == "resolved" and a.reviewer_decision == "approve" for a in existing):
            return []

        if any(a.status == "pending" for a in existing):
            action_id: str | None = next(a.action_id for a in existing if a.status == "pending")
        else:
            # 首次：创建 escalate 动作（幂等）
            action_id = readiness._find_pending_action_id(
                ctx, stage, source_type="expert_review", source_id="critical_tier_review"
            )
            if action_id is None:
                action = PendingHumanAction(
                    action_id=str(uuid.uuid4())[:8],
                    session_id=ctx.session_id,
                    stage_id=stage,
                    source_type="expert_review",
                    source_id="critical_tier_review",
                    action_type="escalate",
                    title="CRITICAL 风险项目专家复核",
                    description=(
                        "项目判定为 CRITICAL 风险等级，必须经专家复核批准后才能通过 Stage 3。"
                        f" 依据：{profile.rationale}"
                    ),
                    risk_level="critical",
                    trigger_reason=profile.rationale,
                    blocking=True,
                )
                ctx.pending_actions.append(action)
                action_id = action.action_id

        blocker = readiness._blocker(
            ctx=ctx,
            stage=stage,
            blocker_type="expert_review",
            severity="critical",
            message="CRITICAL 风险项目须专家复核批准方可推进 Stage 3。",
            source_type="expert_review",
            source_id="critical_tier_review",
            action_id=action_id,
            required_resolution="approve_expert_review",
            can_be_overridden_by_approval=True,
            metadata={"risk_tier": "critical", "profile_rationale": profile.rationale},
        )
        return [blocker.model_copy(update={"rule_id": self.rule_id})]


rule = ExpertReviewRule()
