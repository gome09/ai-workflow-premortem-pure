"""Context schema migration: v0.9.0 → v0.10.0.

Adds business-closure collections (risk treatments and project approvals).
Both default to empty lists, so existing context_json remains loadable.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

FROM_VERSION = "0.9.0"
TO_VERSION = "0.10.0"


def migrate_v090_to_v100(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade v0.9.0 context_json to v0.10.0 — adds closure collections."""
    ctx = deepcopy(raw or {})
    now = datetime.utcnow().isoformat()
    warnings: list[str] = list(ctx.get("migration_warnings") or [])

    ctx.setdefault("risk_treatments", [])
    ctx.setdefault("project_approvals", [])

    ctx["context_schema_version"] = TO_VERSION
    ctx["last_migrated_at"] = now
    history = list(ctx.get("migration_history") or [])
    history.append(
        {
            "from_version": FROM_VERSION,
            "to_version": TO_VERSION,
            "migration_name": "migrate_v090_to_v100",
            "migrated_at": now,
            "warnings": warnings,
        }
    )
    ctx["migration_history"] = history
    ctx["migration_warnings"] = warnings
    return ctx
