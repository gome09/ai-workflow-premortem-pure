# tests/test_migration_upgrade_path.py
"""Milestone 1 P5: Alembic 迁移升级 / 回滚路径验证（CI blocking）。

验收：
- 受支持的旧版本（V008）可以升级到 head（V011），并补齐 V009/V010/V011 新增列。
- downgrade 回 V008 后新增列消失，再次 upgrade head 可恢复。
- 缺少真实 PostgreSQL 时，production-safety CI job（PRODUCTION_SAFETY_REQUIRED=1）
  必须失败而不是跳过；普通单元测试 job 允许跳过，避免离线全量测试依赖外部服务。
"""

from __future__ import annotations

import os

import pytest

_REQUIRED = os.environ.get("PRODUCTION_SAFETY_REQUIRED") == "1"
_DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "")

if not _DATABASE_URL:
    message = (
        "Migration upgrade path test requires E2E_DATABASE_URL pointing at a disposable PostgreSQL."
    )
    if _REQUIRED:
        pytest.fail(message, pytrace=False)
    pytest.skip(message, allow_module_level=True)

from pathlib import Path  # noqa: E402

import psycopg  # noqa: E402
from alembic.config import Config  # noqa: E402

from alembic import command  # noqa: E402
from core.config import settings  # noqa: E402


def _normalize(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _alembic_config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


def _reset_schema() -> None:
    with psycopg.connect(_DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


def _version() -> str:
    with psycopg.connect(_DATABASE_URL) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return "" if row is None else str(row[0])


def _session_columns() -> set[str]:
    with psycopg.connect(_DATABASE_URL) as conn:
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'sessions'
            """
        ).fetchall()
    return {str(row[0]) for row in rows}


def _eval_run_columns() -> set[str]:
    with psycopg.connect(_DATABASE_URL) as conn:
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'eval_runs'
            """
        ).fetchall()
    return {str(row[0]) for row in rows}


@pytest.fixture
def migrated_database():
    assert _normalize(settings.postgres_dsn_sync) == _normalize(_DATABASE_URL), (
        "alembic/env.py derives the URL from settings.postgres_dsn_sync; "
        "POSTGRES_* env must match E2E_DATABASE_URL for this destructive test."
    )
    _reset_schema()
    config = _alembic_config()
    command.upgrade(config, "V008")
    yield config
    # Leave the CI database at head for the PostgreSQL + Redis workflow E2E step.
    command.upgrade(config, "head")


def test_v008_to_head_adds_projection_and_digest_columns(migrated_database):
    config = migrated_database

    assert _version() == "V008"
    columns = _session_columns()
    assert "projection_state" not in columns
    assert "context_digest" not in columns
    eval_columns = _eval_run_columns()
    assert "execution_kind" not in eval_columns
    assert "execution_outcome" not in eval_columns
    assert "evaluation_version_digest" not in eval_columns
    assert "target_endpoint" not in eval_columns

    command.upgrade(config, "head")

    assert _version() == "V011"
    columns = _session_columns()
    assert "projection_state" in columns
    assert "context_digest" in columns
    eval_columns = _eval_run_columns()
    assert "execution_kind" in eval_columns
    assert "execution_outcome" in eval_columns
    assert "evaluation_version_digest" in eval_columns
    assert "target_endpoint" in eval_columns


def test_downgrade_to_v008_then_reupgrade_restores_head(migrated_database):
    config = migrated_database

    command.downgrade(config, "V008")
    assert _version() == "V008"
    columns = _session_columns()
    assert "projection_state" not in columns
    assert "context_digest" not in columns
    eval_columns = _eval_run_columns()
    assert "execution_kind" not in eval_columns
    assert "target_endpoint" not in eval_columns

    command.upgrade(config, "head")
    assert _version() == "V011"
    columns = _session_columns()
    assert "projection_state" in columns
    assert "context_digest" in columns
    eval_columns = _eval_run_columns()
    assert "execution_kind" in eval_columns
    assert "target_endpoint" in eval_columns
