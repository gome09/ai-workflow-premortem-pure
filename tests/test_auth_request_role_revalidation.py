"""T04: every human request revalidates the current DB member role."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from auth.jwt import create_access_token, create_refresh_token
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore
from tests.auth_seed import seed_sqlite_user

TENANT = "tenant-a"
USER = "admin-user"


@pytest.fixture
def auth_env(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "auth.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    seed_sqlite_user(store, user_id=USER, tenant_id=TENANT, role="admin")

    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
        patch("auth.service.session_store", store),
    ):
        from api.main import app

        yield app, store


def _headers(role: str = "admin", *, tenant: str = TENANT, user: str = USER) -> dict:
    token = create_access_token({"sub": user, "tenant_id": tenant, "role": role})
    return {"Authorization": f"Bearer {token}"}


def _demote(store: SQLiteSessionStore, role: str) -> None:
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute("UPDATE users SET role=? WHERE user_id=?", (role, USER))
        conn.commit()


def test_old_admin_token_cannot_create_or_delete_after_demotion(auth_env) -> None:
    app, store = auth_env
    client = TestClient(app)
    created = client.post("/sessions/", json={}, headers=_headers("admin"))
    assert created.status_code == 200

    _demote(store, "viewer")

    # 旧 token 的 role=admin 不再生效：读取按 viewer 允许，写操作被拒。
    assert client.get("/sessions/", headers=_headers("admin")).status_code == 200
    assert client.post("/sessions/", json={}, headers=_headers("admin")).status_code == 403
    assert (
        client.delete(
            f"/sessions/{created.json()['session_id']}", headers=_headers("admin")
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/auth/service-tokens", json={"name": "ci"}, headers=_headers("admin")
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/sessions/{created.json()['session_id']}/data-classification",
            json={"data_classification": "sensitive_personal"},
            headers=_headers("admin"),
        ).status_code
        == 403
    )


def test_refresh_reissues_access_with_current_role(auth_env) -> None:
    app, store = auth_env
    client = TestClient(app)
    _demote(store, "viewer")
    refresh = create_refresh_token({"sub": USER, "tenant_id": TENANT, "role": "admin"})

    response = client.post("/auth/refresh", json={"refresh_token": refresh})

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"


def test_deleted_member_and_tenant_mismatch_are_rejected(auth_env) -> None:
    app, store = auth_env
    client = TestClient(app)

    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute("DELETE FROM users WHERE user_id=?", (USER,))
        conn.commit()

    assert client.get("/sessions/", headers=_headers("admin")).status_code == 401

    seed_sqlite_user(store, user_id="other-user", tenant_id="tenant-b", role="admin")
    assert (
        client.get(
            "/sessions/",
            headers=_headers("admin", tenant="tenant-b", user="other-user"),
        ).status_code
        == 200
    )
    mismatched = _headers("admin", tenant="tenant-b", user="admin-user")
    seed_sqlite_user(store, user_id="admin-user", tenant_id=TENANT, role="admin")
    assert client.get("/sessions/", headers=mismatched).status_code == 403


def test_invalid_db_role_and_db_failure_fail_closed(auth_env, monkeypatch) -> None:
    app, store = auth_env
    client = TestClient(app)
    _demote(store, "owner")

    assert client.get("/sessions/", headers=_headers("admin")).status_code == 401

    def explode(user_id: str):
        raise RuntimeError("database down")

    monkeypatch.setattr(store, "get_user_by_id", explode)
    assert client.get("/sessions/", headers=_headers("admin")).status_code == 503


def test_dependency_is_cached_per_request(auth_env, monkeypatch) -> None:
    app, store = auth_env
    client = TestClient(app)
    calls = {"n": 0}
    original = store.get_user_by_id

    def counted(user_id: str):
        calls["n"] += 1
        return original(user_id)

    monkeypatch.setattr(store, "get_user_by_id", counted)
    assert client.get("/sessions/", headers=_headers("admin")).status_code == 200
    assert calls["n"] == 1


async def test_blocking_lookup_does_not_block_event_loop(auth_env, monkeypatch) -> None:
    app, store = auth_env
    original = store.get_user_by_id

    def slow(user_id: str):
        time.sleep(0.2)
        return original(user_id)

    monkeypatch.setattr(store, "get_user_by_id", slow)
    ticks = 0
    stop = asyncio.Event()

    async def ticker() -> None:
        nonlocal ticks
        while not stop.is_set():
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sessions/", headers=_headers("admin"))
    stop.set()
    await task

    assert response.status_code == 200
    assert ticks >= 3
