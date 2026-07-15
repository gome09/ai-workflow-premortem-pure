# core/migrations/v070_to_v080.py
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

FROM_VERSION = "0.7.0"
TO_VERSION = "0.8.0"


def migrate_v070_to_v080(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade v0.7.0 context_json to v0.8.0 — adds data_classification field.

    Scenario sessions (selected_scenario_id is not None) are backfilled to
    'public_demo'; all other sessions default to 'business_internal'.
    """
    ctx = deepcopy(raw or {})
    now = datetime.utcnow().isoformat()
    warnings: list[str] = list(ctx.get("migration_warnings") or [])

    if "data_classification" not in ctx:
        if ctx.get("selected_scenario_id"):
            ctx["data_classification"] = "public_demo"
        else:
            ctx["data_classification"] = "business_internal"

    ctx["context_schema_version"] = TO_VERSION
    ctx["last_migrated_at"] = now
    history = list(ctx.get("migration_history") or [])
    history.append(
        {
            "from_version": FROM_VERSION,
            "to_version": TO_VERSION,
            "migration_name": "migrate_v070_to_v080",
            "migrated_at": now,
            "warnings": warnings,
        }
    )
    ctx["migration_history"] = history
    ctx["migration_warnings"] = warnings
    return ctx
