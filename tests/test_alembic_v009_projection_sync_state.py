from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "V009_projection_sync_state.py"
)


class _OperationRecorder:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def _load_migration(recorder: _OperationRecorder) -> ModuleType:
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = recorder  # type: ignore[attr-defined]
    previous = sys.modules.get("alembic")
    sys.modules["alembic"] = fake_alembic
    try:
        spec = importlib.util.spec_from_file_location("alembic_v009_under_test", MIGRATION_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = previous


def _normalized(value: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(value)).strip().lower()
    return re.sub(r"\s*([(),;])\s*", r"\1", normalized)


def test_v009_follows_v008_migration() -> None:
    migration = _load_migration(_OperationRecorder())

    assert migration.revision == "V009"
    assert migration.down_revision == "V008"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_v009_upgrade_adds_projection_state_and_eval_run_columns() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()
    sql = _normalized(";".join(recorder.statements))

    assert (
        "alter table sessions add column if not exists "
        "projection_state jsonb not null default '{}'" in sql
    )
    assert (
        "alter table eval_runs add column if not exists "
        "pass_criteria jsonb not null default '[]'" in sql
    )
    assert "alter table eval_runs add column if not exists llm_judge_suggestion jsonb" in sql


def test_v009_downgrade_drops_added_columns() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.downgrade()
    statements = [_normalized(statement) for statement in recorder.statements]

    assert statements == [
        "alter table eval_runs drop column if exists llm_judge_suggestion",
        "alter table eval_runs drop column if exists pass_criteria",
        "alter table sessions drop column if exists projection_state",
    ]
