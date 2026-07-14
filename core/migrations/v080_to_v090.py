"""Context schema migration: v0.8.0 → v0.9.0.

Adds LLM usage counters (llm_call_count, llm_token_estimate).
Backfills 0 for existing sessions; historical usage is NOT reconstructed.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

FROM_VERSION = "0.8.0"
TO_VERSION = "0.9.0"


def migrate_v080_to_v090(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade v0.8.0 context_json to v0.9.0 — adds LLM usage counters."""
    ctx = deepcopy(raw or {})
    now = datetime.utcnow().isoformat()
    warnings: list[str] = list(ctx.get("migration_warnings") or [])

    ctx.setdefault("llm_call_count", 0)
    ctx.setdefault("llm_token_estimate", 0)

    ctx["context_schema_version"] = TO_VERSION
    ctx["last_migrated_at"] = now
    history = list(ctx.get("migration_history") or [])
    history.append(
        {
            "from_version": FROM_VERSION,
            "to_version": TO_VERSION,
            "migration_name": "migrate_v080_to_v090",
            "migrated_at": now,
            "warnings": warnings,
        }
    )
    ctx["migration_history"] = history
    ctx["migration_warnings"] = warnings
    return ctx
