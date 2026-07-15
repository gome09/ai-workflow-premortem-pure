# graph/transition_policy.py
from __future__ import annotations

from dataclasses import dataclass

from core.models import PendingHumanAction


@dataclass(frozen=True)
class ResolutionEffect:
    """人工动作处理结果对流程推进的影响。"""

    allow_resolve: bool
    allow_continue: bool
    require_revision: bool = False
    require_escalation: bool = False
    message: str = ""


class TransitionPolicyError(ValueError):
    """人工动作处理不符合状态迁移策略。"""


STRUCTURED_EDIT_SOURCE_TYPES = {"parser", "policy_gap", "evidence_gap", "eval_coverage"}
STRUCTURED_STAGE_SCHEMA_KEYS = {"failure_modes", "workflow_nodes", "test_cases", "trigger_methods"}


def _has_structured_stage_payload(payload_after: dict | None) -> bool:
    if not payload_after:
        return False
    structured = payload_after.get("structured_output")
    if isinstance(structured, dict) and structured:
        return True
    return any(key in payload_after for key in STRUCTURED_STAGE_SCHEMA_KEYS)


def evaluate_action_resolution(
    action: PendingHumanAction,
    decision: str,
    payload_after: dict | None = None,
) -> ResolutionEffect:
    """
    根据 action_type + reviewer decision 判断是否允许关闭该动作。
    """
    decision = (decision or "").strip()
    action_type = str(action.action_type)

    if action_type == "verify_evidence":
        if decision in {"verify_evidence", "verified", "approve"}:
            return ResolutionEffect(True, True, message="证据/不确定项已核验。")
        if decision in {"dismiss", "dismissed", "reject"}:
            return ResolutionEffect(True, True, message="不确定项已忽略，审计记录保留。")

    if action_type == "approve":
        if decision == "approve":
            return ResolutionEffect(True, True, message="高风险项已人工批准。")
        if decision == "reject":
            return ResolutionEffect(
                True,
                False,
                require_revision=True,
                message="高风险项被驳回，需要修改或回退当前阶段后才能继续。",
            )

    if action_type == "edit":
        if decision == "edit":
            if not payload_after:
                return ResolutionEffect(
                    False,
                    False,
                    require_revision=True,
                    message="edit 动作必须提交 payload_after，不能空编辑通过。",
                )
            if str(
                action.source_type
            ) in STRUCTURED_EDIT_SOURCE_TYPES and not _has_structured_stage_payload(payload_after):
                return ResolutionEffect(
                    False,
                    False,
                    require_revision=True,
                    message=(
                        "parser/policy/evidence/eval_coverage 类 edit 必须提交完整 structured_output；"
                        "仅 edited_text 或备注不能解除阶段推进 blocker。"
                    ),
                )
            return ResolutionEffect(True, True, message="已采用人工编辑版本。")
        if decision == "reject":
            return ResolutionEffect(
                True,
                False,
                require_revision=True,
                message="编辑动作被驳回，需要重跑或回退当前阶段。",
            )

    if action_type == "escalate":
        if decision == "approve":
            return ResolutionEffect(True, True, message="升级风险已被明确批准。")
        if decision == "escalate":
            return ResolutionEffect(
                False,
                False,
                require_escalation=True,
                message="升级风险仍需专家/负责人明确 approve，不能仅标记 escalate 后继续。",
            )
        return ResolutionEffect(
            False,
            False,
            require_escalation=True,
            message="升级风险不能通过 reject/dismissed 普通关闭，需要明确 approve 或回退修改。",
        )

    return ResolutionEffect(False, False, message=f"不支持的动作处理组合：{action_type}/{decision}")


def assert_action_resolution_allowed(
    action: PendingHumanAction,
    decision: str,
    payload_after: dict | None = None,
) -> ResolutionEffect:
    effect = evaluate_action_resolution(action, decision, payload_after=payload_after)
    if not effect.allow_resolve:
        raise TransitionPolicyError(effect.message)
    return effect


# Stage advancement is evaluated by the unified readiness service so the graph,
# API, frontend, and report explain the same gate. Keep these imports at the end
# of the module to preserve the public action-resolution helpers above.
from core.stage_readiness_service import evaluate_stage_gate as evaluate_stage_gate  # noqa: E402
from core.stage_readiness_service import stage_can_continue as stage_can_continue  # noqa: E402
