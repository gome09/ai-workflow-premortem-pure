from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "V008_query_write_optimization.py"
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
        spec = importlib.util.spec_from_file_location("alembic_v008_under_test", MIGRATION_PATH)
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


def test_v008_follows_interrupt_resume_outbox_migration() -> None:
    migration = _load_migration(_OperationRecorder())

    assert migration.revision == "V008"
    assert migration.down_revision == "V007"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_v008_upgrade_adds_version_generated_columns_and_indexes() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()
    sql = _normalized(";".join(recorder.statements))

    assert "add column if not exists version bigint not null default 0" in sql

    for column in (
        "data_classification",
        "selected_scenario_id",
        "session_name",
        "scenario_name",
        "research_target",
        "domain",
    ):
        assert (
            f"add column if not exists {column} text generated always as"
            "(context_json->>'" + column + "')stored" in sql
        )

    assert (
        "create index if not exists idx_sessions_tenant_updated "
        "on sessions(tenant_id,updated_at desc)" in sql
    )
    assert (
        "create index if not exists idx_sessions_tenant_classification "
        "on sessions(tenant_id,data_classification,selected_scenario_id)" in sql
    )
    assert "create index if not exists idx_users_tenant on users(tenant_id)" in sql
    assert (
        "create index if not exists idx_human_actions_session_tenant_status "
        "on human_actions(session_id,tenant_id,status)" in sql
    )


def test_v008_upgrade_backfills_tenant_and_normalizes_stage_id() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()
    sql = _normalized(";".join(recorder.statements))

    assert (
        "update human_actions as h set tenant_id = s.tenant_id from sessions as s "
        "where h.session_id = s.session_id and h.tenant_id is null" in sql
    )
    assert "alter column stage_id type integer" in sql
    assert "alter table interrupt_records" in sql
    assert "when stage_id ~ '^[0-9]+$' then stage_id::integer" in sql


def test_v008_upgrade_uses_not_valid_constraints() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.upgrade()
    sql = _normalized(";".join(recorder.statements))

    for constraint_name in (
        "human_actions_status_check",
        "eval_runs_status_check",
        "redteam_cases_status_check",
        "interrupt_records_status_check",
    ):
        assert constraint_name in sql
    assert sql.count("not valid") >= 5  # four CHECKs + the sessions tenant FK
    assert "add constraint fk_sessions_tenant" in sql
    assert "references tenants(tenant_id)not valid" in sql


def test_v008_downgrade_reverses_in_reverse_dependency_order() -> None:
    recorder = _OperationRecorder()
    migration = _load_migration(recorder)
    migration.downgrade()
    statements = [_normalized(statement) for statement in recorder.statements]

    assert statements[0] == "alter table sessions drop constraint if exists fk_sessions_tenant"
    assert statements[-1] == "alter table sessions drop column if exists version"
    assert "drop index if exists idx_sessions_tenant_updated" in statements
    assert (
        "alter table interrupt_records alter column stage_id type text "
        "using stage_id::text" in statements
    )
