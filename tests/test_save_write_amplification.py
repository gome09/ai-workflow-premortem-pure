"""save() 写放大保护：内容未变化时不再重写整份 context_json。

两个后端都必须：
- 在 sessions 行存内容指纹（context_digest）；
- 指纹相同 → 只推进状态 / 时间 / 版本，不重写 context_json；
- 内容变化 → 重写 context_json 并刷新指纹；
- load() 的 updated_at 来自 sessions 列（context_json 不再携带该易变字段）。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any

import pytest

from core.models import ProjectContext
from storage.backends import postgres as pg
from storage.backends.sqlite_store import SQLiteSessionStore

TENANT = "tenant-a"
SESSION = "s-wa"


@pytest.fixture
def sqlite_store(tmp_path) -> SQLiteSessionStore:
    store = SQLiteSessionStore(str(tmp_path / "write.db"))
    store.initialize()
    return store


def _raw_row(store: SQLiteSessionStore, columns: str) -> dict[str, Any]:
    conn = sqlite3.connect(store._db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            f"SELECT {columns} FROM sessions WHERE session_id=?",  # noqa: S608
            (SESSION,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def test_sqlite_unchanged_save_skips_context_json(sqlite_store):
    ctx = ProjectContext(session_id=SESSION, tenant_id=TENANT, session_name="demo")
    sqlite_store.save(ctx)
    before = _raw_row(sqlite_store, "context_json, context_digest")

    sqlite_store.save(ctx)
    after = _raw_row(sqlite_store, "context_json, context_digest")

    assert after["context_json"] == before["context_json"]
    assert after["context_digest"] == before["context_digest"]
    assert "updated_at" not in json.loads(after["context_json"])


def test_sqlite_changed_content_rewrites_context_json(sqlite_store):
    ctx = ProjectContext(session_id=SESSION, tenant_id=TENANT, session_name="demo")
    sqlite_store.save(ctx)
    before = _raw_row(sqlite_store, "context_json, context_digest")

    ctx.user_materials = ["new material"]
    sqlite_store.save(ctx)
    after = _raw_row(sqlite_store, "context_json, context_digest")

    assert after["context_json"] != before["context_json"]
    assert after["context_digest"] != before["context_digest"]
    loaded = sqlite_store.load(SESSION, TENANT)
    assert loaded is not None
    assert loaded.user_materials == ["new material"]


def test_sqlite_legacy_row_without_digest_is_rewritten(sqlite_store):
    ctx = ProjectContext(session_id=SESSION, tenant_id=TENANT)
    sqlite_store.save(ctx)
    conn = sqlite3.connect(sqlite_store._db_path)
    try:
        conn.execute("UPDATE sessions SET context_digest=NULL WHERE session_id=?", (SESSION,))
        conn.commit()
    finally:
        conn.close()

    sqlite_store.save(ctx)

    assert _raw_row(sqlite_store, "context_digest")["context_digest"]


def test_sqlite_load_reads_updated_at_from_sessions_column(sqlite_store):
    ctx = ProjectContext(session_id=SESSION, tenant_id=TENANT)
    sqlite_store.save(ctx)

    loaded = sqlite_store.load(SESSION, TENANT)

    assert loaded is not None
    assert loaded.updated_at.isoformat() == _raw_row(sqlite_store, "updated_at")["updated_at"]


# ── PostgreSQL：用记录型假连接断言 SQL 分支 ────────────────────────────────


class _Result:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row

    def fetchall(self) -> list[dict[str, Any]]:
        return []


class _Cursor:
    def __init__(self) -> None:
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        self.executemany_calls.append((sql, rows))

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _RecordingConnection:
    """模拟 sessions 行：首次 INSERT 后记住状态，后续 UPDATE 复用。"""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self._exists = False
        self._state: dict[str, Any] = {}
        self._digest = ""

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _Result:
        self.statements.append(sql)
        if "SELECT version, tenant_id::text" in sql:
            if not self._exists:
                return _Result(None)
            return _Result(
                {
                    "version": 0,
                    "tenant_id": TENANT,
                    "projection_state": self._state,
                    "context_digest": self._digest,
                }
            )
        if "INSERT INTO sessions" in sql:
            assert params is not None
            self._exists = True
            self._state = json.loads(str(params[4]))
            self._digest = str(params[5])
        return _Result(None)

    def cursor(self) -> _Cursor:
        return _Cursor()

    def commit(self) -> None:
        return None


@contextmanager
def _conn_ctx(conn: _RecordingConnection):
    yield conn


def _postgres_store(monkeypatch) -> tuple[pg.PostgresSessionStore, _RecordingConnection]:
    conn = _RecordingConnection()
    store = pg.PostgresSessionStore()
    monkeypatch.setattr(store, "_get_conn", lambda: _conn_ctx(conn))
    return store, conn


def test_postgres_unchanged_save_skips_context_json(monkeypatch):
    store, conn = _postgres_store(monkeypatch)
    ctx = ProjectContext(session_id=SESSION, tenant_id=TENANT, session_name="demo")

    store.save(ctx)
    store.save(ctx)

    updates = [sql for sql in conn.statements if "UPDATE sessions" in sql]
    assert len(updates) == 1
    assert "context_json" not in updates[0]
    assert "version          = version + 1" in updates[0]


def test_postgres_changed_content_rewrites_context_json(monkeypatch):
    store, conn = _postgres_store(monkeypatch)
    ctx = ProjectContext(session_id=SESSION, tenant_id=TENANT, session_name="demo")
    store.save(ctx)

    ctx.user_materials = ["new material"]
    store.save(ctx)

    updates = [sql for sql in conn.statements if "UPDATE sessions" in sql]
    assert len(updates) == 1
    assert "context_json" in updates[0]
    assert "context_digest" in updates[0]


def test_postgres_insert_persists_digest(monkeypatch):
    store, conn = _postgres_store(monkeypatch)
    ctx = ProjectContext(session_id=SESSION, tenant_id=TENANT)

    store.save(ctx)

    inserts = [sql for sql in conn.statements if "INSERT INTO sessions" in sql]
    assert inserts
    assert "context_digest" in inserts[0]
