# core/gates/rules/expert_review.py
"""Expert review gate rule — consumes Stage3GateProfile.require_expert_review.

CRITICAL 档 ``require_expert_review=True`` 时，Stage 3 评估创建一条
``escalate`` 阻断动作，并把当时的风险输入摘要写入 ``payload_before``。
只有与当前摘要一致、且经 admin 独立批准的已解决动作才能放行；风险输入
变化后，旧的 pending / approved 动作都不再有效。
"""

from __future__ import annotations

import core.stage_readiness_service as readiness
from core.audit_service import append_audit_event
from core.gates.risk_profile import build_stage3_gate_profile
from core.governance.expert_review import (
    EXPERT_REVIEW_SOURCE_ID,
    EXPERT_REVIEW_SOURCE_TYPE,
)
from core.ids import new_id
from core.models import HumanActionStatus, PendingHumanAction, ProjectContext
from core.risk.assessment import risk_assessment_digest


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
        current_digest = risk_assessment_digest(ctx)
        existing = [
            a
            for a in ctx.pending_actions
            if a.source_type == EXPERT_REVIEW_SOURCE_TYPE
            and a.stage_id == stage
            and a.stage_output_version == current_version
        ]

        # 已按当前风险摘要批准 → 不阻断
        approved = next(
            (
                a
                for a in existing
                if a.status == HumanActionStatus.RESOLVED.value
                and a.reviewer_decision == "approve"
                and (a.payload_before or {}).get("risk_assessment_digest") == current_digest
            ),
            None,
        )
        if approved is not None:
            return []

        pending = next(
            (
                a
                for a in existing
                if a.status == HumanActionStatus.PENDING.value
                and (a.payload_before or {}).get("risk_assessment_digest") == current_digest
            ),
            None,
        )
        if pending is None:
            # 风险输入已变化：废弃旧摘要的 pending 动作，避免它们被误批准。
            for stale in existing:
                if stale.status != HumanActionStatus.PENDING.value:
                    continue
                before = stale.model_dump(mode="json")
                stale.status = HumanActionStatus.SUPERSEDED.value
                append_audit_event(
                    ctx,
                    actor="system",
                    event_type="human_action_superseded",
                    target_type="human_action",
                    target_id=stale.action_id,
                    before=before,
                    after=stale,
                    metadata={
                        "reason": "risk assessment changed; expert review must be re-issued",
                        "stage_id": stage,
                        "stage_output_version": current_version,
                        "stale_digest": (stale.payload_before or {}).get("risk_assessment_digest"),
                        "current_digest": current_digest,
                    },
                )

        if pending is not None:
            action_id = pending.action_id
        else:
            found_action_id = readiness._find_pending_action_id(
                ctx,
                stage,
                source_type=EXPERT_REVIEW_SOURCE_TYPE,
                source_id=EXPERT_REVIEW_SOURCE_ID,
            )
            if found_action_id is None:
                action = PendingHumanAction(
                    action_id=new_id(),
                    session_id=ctx.session_id,
                    stage_id=stage,
                    source_type=EXPERT_REVIEW_SOURCE_TYPE,
                    source_id=EXPERT_REVIEW_SOURCE_ID,
                    action_type="escalate",
                    title="CRITICAL 风险项目专家复核",
                    description=(
                        "项目判定为 CRITICAL 风险等级，必须经 admin 专家复核批准后才能通过 Stage 3。"
                        f" 依据：{profile.rationale}"
                    ),
                    risk_level="critical",
                    trigger_reason=profile.rationale,
                    blocking=True,
                    payload_before={
                        "risk_assessment_digest": current_digest,
                        "risk_tier": "critical",
                    },
                )
                ctx.pending_actions.append(action)
                action_id = action.action_id
            else:
                action_id = found_action_id

        blocker = readiness._blocker(
            ctx=ctx,
            stage=stage,
            blocker_type="expert_review",
            severity="critical",
            message="CRITICAL 风险项目须 admin 专家复核批准方可推进 Stage 3。",
            source_type=EXPERT_REVIEW_SOURCE_TYPE,
            source_id=EXPERT_REVIEW_SOURCE_ID,
            action_id=action_id,
            required_resolution="approve_expert_review",
            can_be_overridden_by_approval=True,
            metadata={
                "risk_tier": "critical",
                "profile_rationale": profile.rationale,
                "risk_assessment_digest": current_digest,
            },
        )
        return [blocker.model_copy(update={"rule_id": self.rule_id})]


rule = ExpertReviewRule()
