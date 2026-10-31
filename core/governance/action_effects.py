# core/governance/action_effects.py
"""Cross-domain effects of resolving a human action.

Keeping these effects in one explicit module prevents the action state machine
from accumulating hidden imports of Evidence, Redteam, Evaluation and Trace
services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from core.audit_service import append_audit_event
from core.governance.action_state import bump_stage_output_version
from core.models import FlagStatus, PendingHumanAction, ProjectContext


@dataclass
class ActionPreEffects:
    apply_result: Any | None = None
    reviewed_key: str | None = None
    before_reviewed: Any = None


@dataclass
class ActionPostEffects:
    skip_resolution_logging: bool = False


def apply_pre_resolution_effects(
    ctx: ProjectContext,
    action: PendingHumanAction,
    *,
    decision: str,
    payload_after: dict | None,
) -> ActionPreEffects:
    """Apply structured-output edits before the action is marked resolved."""
    result = ActionPreEffects()
    if action.action_type == "edit" and decision == "edit" and payload_after:
        from core.reviewed_output_service import apply_reviewed_output_with_result

        result.reviewed_key = f"stage_{action.stage_id}"
        result.before_reviewed = ctx.reviewed_outputs.get(result.reviewed_key)
        result.apply_result = apply_reviewed_output_with_result(ctx, action.stage_id, payload_after)
    return result


def apply_post_resolution_effects(
    ctx: ProjectContext,
    action: PendingHumanAction,
    *,
    decision: str,
    note: str,
    pre_effects: ActionPreEffects,
    payload_after: dict | None,
) -> ActionPostEffects:
    """Apply flag/safety/evidence/redteam/trace/edit effects after resolution."""
    post = ActionPostEffects()

    if action.source_type == "flag" and action.source_id:
        for flag in ctx.flagged_items:
            if flag.item_id == action.source_id:
                if decision in {"dismiss", "dismissed", "reject"}:
                    flag.status = FlagStatus.DISMISSED
                else:
                    flag.status = FlagStatus.VERIFIED
                flag.verified_at = action.resolved_at
                flag.note = note
                break

    if action.source_type == "safety_finding" and action.source_id:
        for finding in ctx.safety_findings:
            if finding.finding_id == action.source_id and decision == "approve":
                finding.status = "resolved"
                finding.resolution_note = note or action.reviewer_note or finding.resolution_note
                finding.resolved_at = action.resolved_at
                break

    if action.action_type == "verify_evidence":
        dismiss_decisions = {"dismiss", "dismissed", "reject"}
        if decision in dismiss_decisions:
            # Historic behaviour: verify_evidence dismiss/reject skips the
            # resolution log and human_action_resolved audit.
            post.skip_resolution_logging = True
            return post

        payload = action.payload_before or {}
        sources = list(payload.get("weak_sources", []) or []) + list(
            payload.get("unverified_sources", []) or []
        )
        evidence_ids = {
            source.get("evidence_id")
            for source in sources
            if isinstance(source, dict) and source.get("evidence_id")
        }
        for evidence_id in evidence_ids:
            for ev in ctx.evidence_sources:
                if ev.evidence_id == evidence_id:
                    ev_before = ev.model_dump(mode="json")
                    ev.verified = True
                    ev.verified_by = "user"
                    ev.verified_at = action.resolved_at
                    ev.verification_note = note or action.reviewer_note or ""
                    append_audit_event(
                        ctx,
                        actor="user",
                        event_type="evidence_verified",
                        target_type="evidence_source",
                        target_id=evidence_id,
                        before=ev_before,
                        after=ev,
                        metadata={"note": note, "action_id": action.action_id},
                    )
                    break

    if action.source_type in {"redteam_gap", "redteam_case"} and decision == "approve":
        from core.redteam_service import (
            approve_redteam_case,
            create_redteam_dataset,
            generate_redteam_cases,
            redteam_case_to_eval_case,
        )

        payload = action.payload_before or {}
        gap_type = payload.get("gap_type")

        if gap_type in {"missing_safety_redteam_case", "missing_node_redteam_case"}:
            generated = generate_redteam_cases(ctx, stage=3)
            append_audit_event(
                ctx,
                actor="user",
                event_type="redteam_cases_generated",
                target_type="stage",
                target_id="3",
                after={"generated_count": len(generated), "action_id": action.action_id},
                metadata={"note": note, "gap_type": gap_type},
            )
        elif gap_type == "draft_redteam_case":
            case_id = payload.get("case_id") or action.source_id
            if case_id:
                approved = approve_redteam_case(ctx, case_id, note=note)
                append_audit_event(
                    ctx,
                    actor="user",
                    event_type="redteam_case_approved",
                    target_type="redteam_case",
                    target_id=case_id,
                    after={"status": approved.status, "action_id": action.action_id},
                    metadata={"note": note},
                )
        elif gap_type == "approved_redteam_case_not_synced":
            case_id = payload.get("case_id") or action.source_id
            if case_id:
                synced = redteam_case_to_eval_case(ctx, case_id)
                append_audit_event(
                    ctx,
                    actor="user",
                    event_type="redteam_case_synced_to_eval",
                    target_type="redteam_case",
                    target_id=case_id,
                    after={"eval_id": synced.eval_id, "action_id": action.action_id},
                    metadata={"note": note},
                )
        elif gap_type == "redteam_eval_case_not_in_dataset":
            dataset = create_redteam_dataset(ctx)
            append_audit_event(
                ctx,
                actor="user",
                event_type="redteam_dataset_created",
                target_type="eval_dataset",
                target_id=dataset.dataset_id,
                after={"case_count": len(dataset.case_ids), "action_id": action.action_id},
                metadata={"note": note},
            )

    # Rejecting a redteam_case action must also reject the underlying case; otherwise
    # the redteam coverage gate keeps recomputing a gap for a vanished action.
    if action.source_type == "redteam_case" and decision in {"reject", "dismiss", "dismissed"}:
        from core.redteam_service import get_redteam_case, reject_redteam_case

        payload = action.payload_before or {}
        case_id = payload.get("case_id") or action.source_id
        if case_id:
            try:
                existing_case = get_redteam_case(ctx, case_id)
            except ValueError:
                existing_case = None
            if existing_case is not None and existing_case.status != "rejected":
                rejected = reject_redteam_case(ctx, case_id, note=note)
                append_audit_event(
                    ctx,
                    actor="user",
                    event_type="redteam_case_rejected",
                    target_type="redteam_case",
                    target_id=case_id,
                    after={"status": rejected.status, "action_id": action.action_id},
                    metadata={"note": note},
                )

    if action.source_type == "trace_backfill_gap" and decision == "approve":
        from core.trace_backfill_service import (
            convert_trace_to_eval_case,
            create_dataset_from_failed_traces,
        )

        payload = action.payload_before or {}
        gap_type = payload.get("gap_type")

        if gap_type == "trace_without_eval_case":
            trace_id = payload.get("trace_id") or action.source_id
            if trace_id:
                eval_case = convert_trace_to_eval_case(ctx, trace_id=trace_id)
                append_audit_event(
                    ctx,
                    actor="user",
                    event_type="trace_backfill_converted",
                    target_type="eval_case",
                    target_id=eval_case.eval_id,
                    after={
                        "trace_id": trace_id,
                        "eval_id": eval_case.eval_id,
                        "action_id": action.action_id,
                    },
                    metadata={"note": note},
                )
        elif gap_type == "trace_eval_case_without_dataset":
            dataset = create_dataset_from_failed_traces(ctx)
            append_audit_event(
                ctx,
                actor="user",
                event_type="trace_backfill_dataset_created",
                target_type="eval_dataset",
                target_id=dataset.dataset_id,
                after={"case_count": len(dataset.case_ids), "action_id": action.action_id},
                metadata={"note": note},
            )

    if pre_effects.apply_result is not None:
        from tools.safety_classifier import add_findings_dedup, scan_policy_gaps

        apply_result = pre_effects.apply_result
        if apply_result.applied_to_structured_output:
            new_version = bump_stage_output_version(ctx, action.stage_id)
            apply_result.stage_output_version_after = new_version
            from core.stage_revision_service import (
                invalidate_downstream_stages,
                record_stage_dependency_versions,
            )

            record_stage_dependency_versions(ctx, action.stage_id)
            invalidate_downstream_stages(
                ctx,
                changed_stage=action.stage_id,
                reason=f"Stage output edited by action {action.action_id}.",
                superseded_by=action.action_id,
            )
            from core.governance.action_factory import create_review_actions_for_stage
            from core.governance.action_resolution import supersede_actions_for_stage

            supersede_actions_for_stage(
                ctx,
                stage=action.stage_id,
                reason=f"Stage output edited by action {action.action_id}; stale actions superseded.",
                superseded_by=action.action_id,
            )
            add_findings_dedup(ctx, scan_policy_gaps(ctx, stage_id=action.stage_id))
            if action.stage_id == 3:
                from core.eval_service import sync_eval_cases_from_stage3

                sync_eval_cases_from_stage3(ctx)
            create_review_actions_for_stage(ctx, action.stage_id, stage_output_version=new_version)
        append_audit_event(
            ctx,
            actor="user",
            event_type="stage_output_edited",
            target_type="stage_output",
            target_id=cast(str, pre_effects.reviewed_key),
            before=pre_effects.before_reviewed,
            after=payload_after,
            metadata={
                "action_id": action.action_id,
                "stage_id": action.stage_id,
                "stage_output_version_before": apply_result.stage_output_version_before,
                "stage_output_version_after": apply_result.stage_output_version_after,
                "applied_to_structured_output": apply_result.applied_to_structured_output,
                "parser_error_cleared": apply_result.parser_error_cleared,
                "warnings": apply_result.warnings,
                "source_type": action.source_type,
            },
        )

    return post
