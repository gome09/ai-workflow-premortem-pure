# core/safety_service.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from core.audit_service import append_audit_event
from core.models import HumanActionStatus, ProjectContext, SafetyFinding
from core.oversight_service import resolve_action
from core.scenario_context import current_domain_profile
from tools.taxonomies.mapper import apply_taxonomy_to_safety_finding


def _has_blocking_safety_action(ctx: ProjectContext, finding_id: str) -> bool:
    return any(
        action.source_type == "safety_finding"
        and action.source_id == finding_id
        and action.status == HumanActionStatus.PENDING.value
        and action.blocking
        for action in ctx.pending_actions
    )


def resolve_safety_finding(
    ctx: ProjectContext,
    *,
    finding_id: str,
    status: Literal["resolved", "dismissed"],
    note: str = "",
    actor: str = "user",
) -> SafetyFinding:
    """处理 SafetyFinding，并与派生的人工动作保持一致。"""
    for finding in ctx.safety_findings:
        if finding.finding_id != finding_id:
            continue

        if finding.status != "open":
            raise ValueError(f"Safety finding is not open: {finding_id}")

        severity = str(finding.severity).lower()
        if (
            status == "dismissed"
            and finding.requires_human_review
            and severity in {"high", "critical"}
            and _has_blocking_safety_action(ctx, finding_id)
        ):
            raise ValueError(
                "High/Critical safety findings with blocking actions cannot be dismissed directly; "
                "resolve the corresponding human action instead."
            )

        before = finding.model_dump(mode="json")
        finding.status = status
        finding.resolution_note = note
        finding.resolved_at = datetime.utcnow()
        finding.mitigation_status = "mitigated" if status == "resolved" else "dismissed"
        finding.residual_risk = "low" if status == "resolved" else "unknown"
        apply_taxonomy_to_safety_finding(finding, domain=current_domain_profile(ctx))

        append_audit_event(
            ctx,
            actor=actor,
            event_type=f"safety_finding_{status}",
            target_type="safety_finding",
            target_id=finding_id,
            before=before,
            after=finding,
            metadata={"note": note, "severity": finding.severity, "risk_type": finding.risk_type},
        )

        if status == "resolved":
            for action in list(ctx.pending_actions):
                if (
                    action.source_type == "safety_finding"
                    and action.source_id == finding_id
                    and action.status == HumanActionStatus.PENDING.value
                ):
                    resolve_action(
                        ctx,
                        action_id=action.action_id,
                        decision="approve",
                        note=note or "Safety finding resolved by reviewer.",
                    )

        return finding

    raise ValueError(f"Safety finding not found: {finding_id}")
