"""T06: SQLite write transactions serialize save/purge ordering."""

from __future__ import annotations

import sqlite3

import pytest

from core.models import ProjectContext
from storage.backends.sqlite_store import SQLiteSessionStore

TENANT = "tenant-a"


@pytest.fixture
def store(tmp_path) -> SQLiteSessionStore:
    backend = SQLiteSessionStore(str(tmp_path / "purge-order.db"))
    backend.initialize()
    return backend


def test_begin_immediate_blocks_second_writer(store) -> None:
    first = store._get_conn()  # noqa: SLF001
    second = sqlite3.connect(store._db_path, timeout=0.1)  # noqa: SLF001
    try:
        first.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError):
            second.execute("BEGIN IMMEDIATE")
    finally:
        first.rollback()
        first.close()
        second.close()


def test_purge_and_save_are_serialized_by_immediate(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    store.create(ctx)

    # 事务 A 持有写锁时，purge 的 BEGIN IMMEDIATE 必须等待而不是并发读取。
    blocker = store._get_conn()  # noqa: SLF001
    try:
        blocker.execute("BEGIN IMMEDIATE")
        blocker.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id=?", ("locked", ctx.session_id)
        )
        with pytest.raises(sqlite3.OperationalError):
            contender = sqlite3.connect(store._db_path, timeout=0.1)  # noqa: SLF001
            try:
                contender.execute("BEGIN IMMEDIATE")
            finally:
                contender.close()
    finally:
        blocker.commit()
        blocker.close()

    outcome = store.purge_session(ctx.session_id, TENANT, "admin", {})
    assert outcome.deleted is True
    assert store.load(ctx.session_id, TENANT) is None


def test_purge_failure_keeps_session_and_audit(store, monkeypatch) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    store.create(ctx)

    def explode(summary):
        raise RuntimeError("archive failure")

    monkeypatch.setattr("storage.backends.sqlite_store.sanitize_purge_summary", explode)

    with pytest.raises(RuntimeError, match="archive failure"):
        store.purge_session(ctx.session_id, TENANT, "admin", {})

    assert store.load(ctx.session_id, TENANT) is not None
