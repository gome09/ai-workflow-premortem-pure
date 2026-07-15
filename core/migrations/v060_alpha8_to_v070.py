# core/migrations/v060_alpha8_to_v070.py
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

FROM_VERSION = "0.6.0-alpha.8"
TO_VERSION = "0.7.0"


def migrate_v060_alpha8_to_v070(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade v0.6.0-alpha.8 context_json to the v0.7 reliable-execution schema."""
    ctx = deepcopy(raw or {})
    now = datetime.utcnow().isoformat()
    warnings: list[str] = list(ctx.get("migration_warnings") or [])

    for action in ctx.get("pending_actions") or []:
        if not isinstance(action, dict):
            continue
        stage_id = action.get("stage_id")
        stage_version = action.get("stage_output_version", 1)
        source_type = action.get("source_type") or "unknown"
        source_id = action.get("source_id") or "stage"
        action.setdefault("action_schema_version", TO_VERSION)
        action.setdefault("target_stage", stage_id)
        action.setdefault("target_stage_version", stage_version)
        action.setdefault("target_object_path", f"stage_{stage_id}.{source_type}.{source_id}")
        action.setdefault("idempotency_key", None)
        action.setdefault("expected_before_hash", None)
        action.setdefault("approved_payload_hash", None)
        action.setdefault("resume_token", None)
        action.setdefault("expires_at", None)
        action.setdefault("resolution_attempts", 0)
        action.setdefault("last_resolution_error", None)

    ctx.setdefault("action_resolution_logs", [])
    ctx.setdefault("llm_traces", [])
    ctx["context_schema_version"] = TO_VERSION
    ctx["last_migrated_at"] = now
    history = list(ctx.get("migration_history") or [])
    history.append(
        {
            "from_version": FROM_VERSION,
            "to_version": TO_VERSION,
            "migration_name": "migrate_v060_alpha8_to_v070",
            "migrated_at": now,
            "warnings": warnings,
        }
    )
    ctx["migration_history"] = history
    ctx["migration_warnings"] = warnings
    return ctx
