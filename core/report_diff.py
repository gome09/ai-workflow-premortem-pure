# core/report_diff.py
from __future__ import annotations

from typing import Any

from core.models import ProjectContext


def _dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _related_actions(ctx: ProjectContext, stage: int) -> list[dict[str, Any]]:
    return [
        {
            "action_id": action.action_id,
            "source_type": action.source_type,
            "source_id": action.source_id,
            "action_type": action.action_type,
            "status": action.status,
            "reviewer_decision": action.reviewer_decision,
            "stage_output_version": action.stage_output_version,
            "superseded_by": action.superseded_by,
        }
        for action in ctx.pending_actions
        if action.stage_id == stage
    ]


def _related_audit_events(ctx: ProjectContext, stage: int) -> list[dict[str, Any]]:
    stage_key = f"stage_{stage}"
    related: list[dict[str, Any]] = []
    for event in ctx.audit_events:
        metadata_stage = event.metadata.get("stage_id") if event.metadata else None
        if metadata_stage == stage or event.target_id == stage_key:
            related.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "target_type": event.target_type,
                    "target_id": event.target_id,
                    "created_at": event.created_at.isoformat(),
                    "metadata": event.metadata,
                }
            )
    return related


def build_stage_version_history(ctx: ProjectContext) -> dict[str, dict[str, Any]]:
    """Build an audit-friendly stage version summary for reports."""
    history: dict[str, dict[str, Any]] = {}
    for stage in range(1, 5):
        key = f"stage_{stage}"
        ai_output = _dump(getattr(ctx, f"stage_{stage}_output", None))
        reviewed = ctx.reviewed_outputs.get(key)
        actions = _related_actions(ctx, stage)
        edit_actions = [a for a in actions if a.get("action_type") == "edit"]
        history[key] = {
            "current_version": int(ctx.stage_output_versions.get(key, 1)),
            "has_ai_output": ai_output is not None,
            "has_reviewed_output": reviewed is not None,
            "changed_by_human": reviewed is not None and reviewed != ai_output,
            "open_parser_error": key in ctx.parser_errors,
            "parser_error": ctx.parser_errors.get(key),
            "edit_action_ids": [a["action_id"] for a in edit_actions],
            "pending_action_ids": [a["action_id"] for a in actions if a.get("status") == "pending"],
            "superseded_action_ids": [
                a["action_id"] for a in actions if a.get("status") == "superseded"
            ],
            "related_actions": actions,
            "related_audit_events": _related_audit_events(ctx, stage),
        }
    return history


def build_output_diff_summary(ctx: ProjectContext) -> dict[str, dict[str, Any]]:
    """Backward-compatible alias for older report consumers."""
    return build_stage_version_history(ctx)
