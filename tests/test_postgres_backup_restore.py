# tests/test_postgres_backup_restore.py
"""PostgreSQL dump/restore drill: restored business records remain readable/usable."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REQUIRED = os.environ.get("PRODUCTION_SAFETY_REQUIRED") == "1"
_DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "")
_RESTORE_URL = os.environ.get("E2E_RESTORE_DATABASE_URL", "")

if not _DATABASE_URL or not _RESTORE_URL:
    message = (
        "Backup/restore test requires E2E_DATABASE_URL and E2E_RESTORE_DATABASE_URL "
        "pointing at disposable PostgreSQL databases."
    )
    if _REQUIRED:
        pytest.fail(message, pytrace=False)
    pytest.skip(message, allow_module_level=True)

if shutil.which("pg_dump") is None or shutil.which("psql") is None:
    message = "pg_dump/psql not available on PATH"
    if _REQUIRED:
        pytest.fail(message, pytrace=False)
    pytest.skip(message, allow_module_level=True)

import psycopg  # noqa: E402

from core.models import ProjectContext  # noqa: E402
from storage.backends.postgres import PostgresSessionStore  # noqa: E402
from storage.field_security import is_encryption_enabled  # noqa: E402

_PG_DUMP = shutil.which("pg_dump") or "pg_dump"
_PSQL = shutil.which("psql") or "psql"


def _reset_restore_schema() -> None:
    with psycopg.connect(_RESTORE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


def _run_pg_dump(target: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv, local test tool
        [
            _PG_DUMP,
            "--no-owner",
            "--no-privileges",
            "--format=plain",
            f"--file={target}",
            _DATABASE_URL,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _run_psql_restore(dump: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv, local test tool
        [_PSQL, _RESTORE_URL, "-v", "ON_ERROR_STOP=1", "-f", str(dump)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_dump_restore_preserves_business_record_and_allows_save(tmp_path):
    tenant = "backup-restore-tenant"
    source = PostgresSessionStore()
    ctx = ProjectContext(
        tenant_id=tenant,
        research_target="backup restore target",
        goal="backup restore goal",
        user_materials=["restore-sensitive-sample"],
        data_classification="business_internal",
    )
    source.save(ctx)
    source.close()

    dump = tmp_path / "ai_workflow.dump.sql"
    _run_pg_dump(dump)
    _reset_restore_schema()
    _run_psql_restore(dump)

    restored_store = PostgresSessionStore()
    restored_store._dsn = _RESTORE_URL  # noqa: SLF001 - test-only DSN override
    restored_store._pool = None  # noqa: SLF001
    restored = restored_store.load(ctx.session_id, tenant)
    assert restored is not None
    assert restored.research_target == "backup restore target"
    assert restored.goal == "backup restore goal"
    assert restored.user_materials == ["restore-sensitive-sample"]

    with psycopg.connect(_RESTORE_URL) as conn:
        row = conn.execute(
            "SELECT context_json::text FROM sessions WHERE session_id=%s",
            (ctx.session_id,),
        ).fetchone()
    assert row is not None
    if is_encryption_enabled():
        assert "enc:v1:" in row[0]
        assert "restore-sensitive-sample" not in row[0]

    restored.session_name = "restored-and-continued"
    restored_store.save(restored)
    reloaded = restored_store.load(ctx.session_id, tenant)
    assert reloaded is not None
    assert reloaded.session_name == "restored-and-continued"
    restored_store.close()
