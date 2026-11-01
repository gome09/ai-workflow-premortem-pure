"""V012 structure: workspace invitations and eval case/run bindings."""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "V012_p1_governance.py"
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
        spec = importlib.util.spec_from_file_location("alembic_v012_under_test", MIGRATION_PATH)
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


def test_v012_follows_v011_migration() -> None:
    migration = _load_migration(_OperationRecorder())

    assert migration.revision == "V012"
    assert migration.down_revision == "V011"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_v012_upgrade_adds_invitations_and_bindings() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()

    statements = _normalized(";".join(recorder.statements))
    assert "create table if not exists workspace_invitations" in statements
    assert "idx_workspace_invitations_token_hash" in statements
    assert "idx_workspace_invitations_tenant_status" in statements
    assert "idx_workspace_invitations_tenant_email" in statements
    assert "eval_cases" in statements
    assert "standard_version" in statements
    assert "eval_runs" in statements
    assert "case_version_digest" in statements
    assert "target_deployment_version" in statements


def test_v012_downgrade_removes_new_bindings_and_table() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.downgrade()

    statements = [_normalized(statement) for statement in recorder.statements]
    assert statements == [
        "alter table eval_runs drop column if exists target_deployment_version",
        "alter table eval_runs drop column if exists case_version_digest",
        "alter table eval_cases drop column if exists standard_version",
        "drop table if exists workspace_invitations",
    ]
