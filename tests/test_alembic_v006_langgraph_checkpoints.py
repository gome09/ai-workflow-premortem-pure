from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

from langgraph.checkpoint.postgres.base import BasePostgresSaver

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "V006_langgraph_checkpoints.py"
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
        spec = importlib.util.spec_from_file_location("alembic_v006_under_test", MIGRATION_PATH)
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


def test_v006_follows_current_alembic_head() -> None:
    migration = _load_migration(_OperationRecorder())

    assert migration.revision == "V006"
    assert migration.down_revision == "V005"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_v006_upgrade_matches_langgraph_postgres_3_0_5_schema() -> None:
    assert importlib.metadata.version("langgraph-checkpoint-postgres") == "3.0.5"
    assert len(BasePostgresSaver.MIGRATIONS) == 10

    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()
    sql = _normalized(";".join(recorder.statements))

    # The four upstream CREATE TABLE contracts must be present verbatim after
    # whitespace normalization. V006 creates blobs and writes in their final
    # forms, so the nullable blob and task_path assertions are separate.
    for upstream_sql in BasePostgresSaver.MIGRATIONS[:4]:
        upstream = _normalized(upstream_sql)
        if "checkpoint_blobs" in upstream:
            upstream = upstream.replace("blob bytea not null", "blob bytea")
        if "checkpoint_writes" in upstream:
            upstream = upstream.replace(
                "blob bytea not null,primary key",
                "blob bytea not null,task_path text not null default '',primary key",
            )
        assert upstream in sql

    assert "task_path text not null default ''" in sql
    assert "alter column blob drop not null" in sql
    for index_name in (
        "checkpoints_thread_id_idx",
        "checkpoint_blobs_thread_id_idx",
        "checkpoint_writes_thread_id_idx",
    ):
        assert f"create index if not exists {index_name}" in sql
    assert "generate_series(0,9)" in sql
    assert "on conflict(v)do nothing" in sql
    assert "concurrently" not in sql


def test_v006_downgrade_removes_indexes_then_owned_tables() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.downgrade()
    statements = [_normalized(statement) for statement in recorder.statements]

    assert statements == [
        "drop index if exists checkpoint_writes_thread_id_idx",
        "drop index if exists checkpoint_blobs_thread_id_idx",
        "drop index if exists checkpoints_thread_id_idx",
        "drop table if exists checkpoint_writes",
        "drop table if exists checkpoint_blobs",
        "drop table if exists checkpoints",
        "drop table if exists checkpoint_migrations",
    ]
