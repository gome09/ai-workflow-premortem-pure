from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "V011_business_closure.py"
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
        spec = importlib.util.spec_from_file_location("alembic_v011_under_test", MIGRATION_PATH)
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


def test_v011_follows_v010_migration() -> None:
    migration = _load_migration(_OperationRecorder())

    assert migration.revision == "V011"
    assert migration.down_revision == "V010"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_v011_upgrade_adds_eval_run_execution_columns() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()

    statements = _normalized(";".join(recorder.statements))
    assert "execution_kind" in statements
    assert "execution_outcome" in statements
    assert "evaluation_version_digest" in statements
    assert "target_endpoint" in statements
    assert "eval_runs" in statements


def test_v011_downgrade_drops_eval_run_execution_columns() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.downgrade()

    statements = [_normalized(statement) for statement in recorder.statements]
    assert statements == [
        "alter table eval_runs drop column if exists target_endpoint",
        "alter table eval_runs drop column if exists evaluation_version_digest",
        "alter table eval_runs drop column if exists execution_outcome",
        "alter table eval_runs drop column if exists execution_kind",
    ]
