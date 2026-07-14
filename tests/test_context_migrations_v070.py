"""v0.7 context migration tests.

These tests are intentionally added for the later unified validation pass.
They are not executed as part of this package-generation step.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.migrations import migrate_context

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "contexts"


def test_v060_minimal_context_can_migrate_to_v070_contract():
    raw = json.loads((FIXTURE_DIR / "v060_alpha8_minimal.json").read_text())
    ctx = migrate_context(raw)

    assert ctx.context_schema_version == "0.8.0"
    assert hasattr(ctx, "migration_history")
    assert hasattr(ctx, "action_resolution_logs")
    assert hasattr(ctx, "llm_traces")


def test_v060_actions_receive_v070_contract_fields():
    raw = json.loads((FIXTURE_DIR / "v060_alpha8_with_actions.json").read_text())
    ctx = migrate_context(raw)

    assert ctx.pending_actions
    action = ctx.pending_actions[0]
    assert action.action_schema_version == "0.7.0"
    assert action.action_contract_id
