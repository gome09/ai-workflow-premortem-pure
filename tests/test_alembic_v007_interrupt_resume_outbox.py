from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "V007_interrupt_resume_outbox.py"
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
        spec = importlib.util.spec_from_file_location("alembic_v007_under_test", MIGRATION_PATH)
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


def test_v007_follows_checkpoint_migration() -> None:
    migration = _load_migration(_OperationRecorder())

    assert migration.revision == "V007"
    assert migration.down_revision == "V006"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_v007_upgrade_creates_durable_interrupt_resume_outbox() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()
    sql = _normalized(";".join(recorder.statements))

    assert "create table if not exists interrupt_resume_outbox" in sql
    for column_contract in (
        "interrupt_id text primary key",
        "session_id text not null references sessions(session_id)on delete cascade",
        "tenant_id uuid",
        "action_id text not null unique",
        "thread_id text not null",
        "checkpoint_ns text not null default ''",
        "resume_payload jsonb not null",
        "status text not null default 'pending'",
        "attempts integer not null default 0",
        "claimed_at timestamptz",
        "completed_at timestamptz",
        "last_error text",
        "created_at timestamptz not null default now()",
        "updated_at timestamptz not null default now()",
    ):
        assert column_contract in sql

    assert "check(status in('pending','processing','completed','failed'))" in sql
    assert "check(attempts >= 0)" in sql
    assert "create index if not exists idx_interrupt_resume_outbox_pending" in sql
    assert "on interrupt_resume_outbox(status,updated_at,created_at)" in sql
    assert "where status in('pending','failed')" in sql


def test_v007_downgrade_removes_index_then_table() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.downgrade()

    assert [_normalized(statement) for statement in recorder.statements] == [
        "drop index if exists idx_interrupt_resume_outbox_pending",
        "drop table if exists interrupt_resume_outbox",
    ]
