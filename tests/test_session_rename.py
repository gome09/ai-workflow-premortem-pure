"""会话重命名的持久化、API 权限与输入校验测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")
pytest.importorskip("redis")
pytest.importorskip("langchain_core")
pytest.importorskip("langchain_openai")
pytest.importorskip("tavily")
pytest.importorskip("prometheus_fastapi_instrumentator")

from fastapi.testclient import TestClient

from auth.jwt import create_access_token
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.postgres import PostgresSessionStore
from storage.backends.sqlite_store import SQLiteSessionStore


def _headers(role: str, tenant_id: str = "rename-tenant") -> dict:
    token = create_access_token({"sub": "rename-user", "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def rename_stack(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "rename.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        from api.main import app

        yield TestClient(app), SessionService(), store


def test_rename_session_persists_and_appears_in_list(rename_stack):
    client, service, store = rename_stack
    ctx = service.create_session(tenant_id="rename-tenant")

    response = client.patch(
        f"/sessions/{ctx.session_id}/name",
        json={"name": "  风险评估会话  "},
        headers=_headers("editor"),
    )

    assert response.status_code == 200
    assert response.json() == {"session_id": ctx.session_id, "session_name": "风险评估会话"}
    restored = store.load(ctx.session_id, "rename-tenant")
    assert restored is not None
    assert restored.session_name == "风险评估会话"
    assert restored.audit_events[-1].event_type == "session_renamed"
    assert service.list_sessions(tenant_id="rename-tenant")[0]["session_name"] == "风险评估会话"


def test_rename_session_rejects_blank_and_too_long_names(rename_stack):
    client, service, _ = rename_stack
    ctx = service.create_session(tenant_id="rename-tenant")

    blank = client.patch(
        f"/sessions/{ctx.session_id}/name",
        json={"name": "   "},
        headers=_headers("editor"),
    )
    too_long = client.patch(
        f"/sessions/{ctx.session_id}/name",
        json={"name": "会" * 81},
        headers=_headers("editor"),
    )

    assert blank.status_code == 422
    assert too_long.status_code == 422


def test_rename_session_enforces_role_and_tenant(rename_stack):
    client, service, _ = rename_stack
    ctx = service.create_session(tenant_id="rename-tenant")

    viewer = client.patch(
        f"/sessions/{ctx.session_id}/name",
        json={"name": "无权限"},
        headers=_headers("viewer"),
    )
    other_tenant = client.patch(
        f"/sessions/{ctx.session_id}/name",
        json={"name": "跨租户"},
        headers=_headers("editor", tenant_id="other-tenant"),
    )

    assert viewer.status_code == 403
    assert other_tenant.status_code == 404


def test_postgres_archive_serializes_jsonb_rows_before_inserting():
    class _Connection:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, params):
            self.calls.append((sql, params))
            return self

        def fetchall(self):
            return [
                {
                    "event_id": "evt-1",
                    "actor": "user",
                    "event_type": "session_renamed",
                    "target_type": "session",
                    "target_id": "session-1",
                    "before_hash": "before",
                    "after_hash": "after",
                    "before_snapshot": {"session_name": "旧名称"},
                    "after_snapshot": {"session_name": "新名称"},
                    "metadata": {"source": "test"},
                    "created_at": "2026-09-21T00:00:00Z",
                }
            ]

        def commit(self):
            return None

    store = object.__new__(PostgresSessionStore)
    connection = _Connection()
    store._get_conn = lambda: connection

    assert store.archive_audit_events("session-1", "admin", {"session_name": "新名称"}) == 2
    archived_params = connection.calls[1][1]
    assert archived_params[9] == '{"session_name": "\\u65e7\\u540d\\u79f0"}'
    assert archived_params[10] == '{"session_name": "\\u65b0\\u540d\\u79f0"}'
    assert archived_params[11] == '{"source": "test"}'
