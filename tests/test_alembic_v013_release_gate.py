"""V013 structure: release-gate service tokens and check audit rows."""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "V013_release_gate.py"
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
        spec = importlib.util.spec_from_file_location("alembic_v013_under_test", MIGRATION_PATH)
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


def test_v013_follows_v012_migration() -> None:
    migration = _load_migration(_OperationRecorder())

    assert migration.revision == "V013"
    assert migration.down_revision == "V012"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_v013_upgrade_creates_service_tokens_and_checks() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()

    statements = _normalized(";".join(recorder.statements))
    assert "create table if not exists service_tokens" in statements
    assert "idx_service_tokens_token_hash" in statements
    assert "idx_service_tokens_tenant" in statements
    assert "token_hash" in statements
    assert "expires_at" in statements
    assert "revoked_at" in statements
    assert "last_used_at" in statements
    assert "release_gate:read" in statements
    assert "scope" in statements
    assert "create table if not exists release_gate_checks" in statements
    assert "idx_release_gate_checks_tenant_time" in statements
    assert "idx_release_gate_checks_session" in statements
    assert "evaluation_version_digest" in statements
    assert "evidence_digest" in statements
    assert "decision" in statements
    assert "allow" in statements
    assert "block" in statements


def test_v013_downgrade_drops_tables() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.downgrade()

    statements = [_normalized(statement) for statement in recorder.statements]
    assert statements == [
        "drop table if exists release_gate_checks",
        "drop table if exists service_tokens",
    ]
