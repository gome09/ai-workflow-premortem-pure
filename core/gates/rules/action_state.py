# core/gates/rules/action_state.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import HumanActionStatus, ProjectContext


class ActionStateRule:
    """Direct GateRule: pending/rejected/unresolved human actions block advancement."""

    rule_id = "action_state"
    applies_to_stages = {1, 2, 3, 4}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        version = readiness._current_version(ctx, stage)
        inactive = {HumanActionStatus.CANCELLED.value, HumanActionStatus.SUPERSEDED.value}
        blockers: list[readiness.StageBlocker] = []

        for action in ctx.pending_actions:
            if action.stage_id != stage or action.stage_output_version != version:
                continue

            if action.status == HumanActionStatus.PENDING.value and action.blocking:
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=stage,
                        blocker_type="pending_action",
                        severity=action.risk_level,
                        message=(
                            f"阶段{stage} v{version} 仍有阻断型人工动作未处理："
                            f"{action.action_id} ({action.action_type})。"
                        ),
                        source_type=action.source_type or "human_action",
                        source_id=action.source_id,
                        action_id=action.action_id,
                        required_resolution=(
                            "approve_escalation"
                            if action.action_type == "escalate"
                            else "resolve_action"
                        ),
                        can_be_overridden_by_approval=False,
                        metadata={
                            "action_type": action.action_type,
                            "title": action.title,
                            "trigger_reason": action.trigger_reason,
                            "action_contract_id": action.action_contract_id,
                            "idempotency_key_present": bool(action.idempotency_key),
                        },
                    )
                )
                continue

            if (
                action.status == HumanActionStatus.RESOLVED.value
                and action.reviewer_decision == "reject"
                and action.action_type in {"approve", "edit", "escalate"}
            ):
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=stage,
                        blocker_type="rejected_action",
                        severity=action.risk_level,
                        message=(
                            f"阶段{stage} v{version} 存在被驳回的关键动作："
                            f"{action.action_id}。需要修改或回退后再继续。"
                        ),
                        source_type=action.source_type or "human_action",
                        source_id=action.source_id,
                        action_id=action.action_id,
                        required_resolution="revise_stage",
                        can_be_overridden_by_approval=False,
                        metadata={
                            "reviewer_decision": action.reviewer_decision,
                            "superseded_by": action.superseded_by,
                        },
                    )
                )
                continue

            if (
                action.action_type == "escalate"
                and not (
                    action.status == HumanActionStatus.RESOLVED.value
                    and action.reviewer_decision == "approve"
                )
                and action.status not in inactive
            ):
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=stage,
                        blocker_type="unresolved_escalation",
                        severity=action.risk_level,
                        message=(
                            f"阶段{stage} v{version} 存在未明确批准的升级风险：{action.action_id}。"
                        ),
                        source_type=action.source_type or "human_action",
                        source_id=action.source_id,
                        action_id=action.action_id,
                        required_resolution="approve_escalation",
                        can_be_overridden_by_approval=False,
                        metadata={
                            "action_status": action.status,
                            "reviewer_decision": action.reviewer_decision,
                        },
                    )
                )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = ActionStateRule()
