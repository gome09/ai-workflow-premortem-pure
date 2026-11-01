# core/governance/expert_review.py
"""CRITICAL expert-review approval validation.

专家复核只允许满足以下条件的批准：
- 审核人角色为 admin；
- 审核人身份来自认证令牌（非空）；
- 审核人不是会话创建者（禁止自审批）；
- 审核绑定到当前风险输入摘要（风险因子 / 数据分级 / 有效 override 变化后旧批准失效）。

审核人身份与摘要由 ``action_resolution`` 写入 append-only 审计事件，
因此不需要给 ``human_actions`` 表加列。
"""

from __future__ import annotations

from core.models import PendingHumanAction, ProjectContext
from core.risk.assessment import risk_assessment_digest

EXPERT_REVIEW_SOURCE_TYPE = "expert_review"
EXPERT_REVIEW_SOURCE_ID = "critical_tier_review"
EXPERT_REVIEW_APPROVER_ROLE = "admin"


class ExpertReviewAuthorizationError(PermissionError):
    """Reviewer identity, role, or independence cannot be verified."""


class StaleExpertReviewApprovalError(ValueError):
    """The approval is bound to an older risk assessment state."""


def validate_expert_review_approval(
    ctx: ProjectContext,
    action: PendingHumanAction,
    *,
    decision: str,
    actor_id: str,
    actor_role: str,
) -> str | None:
    """Validate a CRITICAL expert-review approval; return the bound digest.

    Non-expert actions and non-approve decisions return ``None`` so the normal
    transition policy remains the only gate for them.
    """
    if action.source_type != EXPERT_REVIEW_SOURCE_TYPE:
        return None
    if (decision or "").strip() != "approve":
        return None

    reviewer = (actor_id or "").strip()
    if actor_role != EXPERT_REVIEW_APPROVER_ROLE:
        raise ExpertReviewAuthorizationError("CRITICAL expert review approval requires admin role")
    if not reviewer:
        raise ExpertReviewAuthorizationError(
            "Reviewer identity is required for CRITICAL expert review"
        )

    creator = (getattr(ctx, "created_by", "") or "").strip()
    if not creator:
        raise ExpertReviewAuthorizationError(
            "Session creator is not recorded; reviewer independence cannot be verified"
        )
    if reviewer == creator:
        raise ExpertReviewAuthorizationError(
            "Self-approval is not allowed: the reviewer is the session creator"
        )

    expected_digest = (action.payload_before or {}).get("risk_assessment_digest")
    current_digest = risk_assessment_digest(ctx)
    if not expected_digest:
        raise StaleExpertReviewApprovalError(
            "Expert review action has no risk assessment digest; re-run the stage gate"
        )
    if expected_digest != current_digest:
        raise StaleExpertReviewApprovalError(
            "Risk assessment changed since the expert review escalation; re-run the stage gate"
        )
    return current_digest
