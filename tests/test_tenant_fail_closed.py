"""租户 fail-closed 契约。

空 tenant_id 的读取必须拒绝：否则 `session_exists` / `list_projection`
会退化为跨租户直读。跨租户读取只能走显式 `SYSTEM_ACCESS` 内部哨兵。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from auth.jwt import create_access_token, get_current_tenant
from core.models import ProjectContext
from storage.access import SYSTEM_ACCESS
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.errors import TenantIsolationError

TENANT = "tenant-a"
SESSION = "s-tenant"


@pytest.fixture
def seeded_store(tmp_path) -> SQLiteSessionStore:
    store = SQLiteSessionStore(str(tmp_path / "tenant.db"))
    store.initialize()
    store.save(ProjectContext(session_id=SESSION, tenant_id=TENANT))
    return store


def test_sqlite_load_rejects_empty_tenant(seeded_store):
    with pytest.raises(TenantIsolationError):
        seeded_store.load(SESSION)


def test_sqlite_session_exists_rejects_empty_tenant(seeded_store):
    with pytest.raises(TenantIsolationError):
        seeded_store.session_exists(SESSION)


def test_sqlite_list_projection_rejects_empty_tenant(seeded_store):
    with pytest.raises(TenantIsolationError):
        seeded_store.list_projection("human_actions", SESSION)


def test_sqlite_list_sessions_rejects_empty_tenant(seeded_store):
    with pytest.raises(TenantIsolationError):
        seeded_store.list_sessions(limit=10)


def test_sqlite_other_tenant_still_cannot_read(seeded_store):
    assert seeded_store.load(SESSION, "tenant-b") is None
    assert seeded_store.session_exists(SESSION, "tenant-b") is False
    assert seeded_store.list_projection("human_actions", SESSION, "tenant-b") is None


def test_sqlite_system_access_channel_reads_cross_tenant(seeded_store):
    assert seeded_store.load(SESSION, system_access=SYSTEM_ACCESS) is not None
    assert seeded_store.session_exists(SESSION, system_access=SYSTEM_ACCESS) is True
    assert seeded_store.list_projection("human_actions", SESSION, system_access=SYSTEM_ACCESS) == []
    assert seeded_store.list_sessions(limit=10, system_access=SYSTEM_ACCESS)


@pytest.mark.parametrize("forged", [True, False, 1, "system", object()])
def test_sqlite_forged_system_flag_raises(seeded_store, forged):
    with pytest.raises(TenantIsolationError):
        seeded_store.session_exists(SESSION, system_access=forged)  # type: ignore[arg-type]
    with pytest.raises(TenantIsolationError):
        seeded_store.list_projection(
            "human_actions",
            SESSION,
            system_access=forged,  # type: ignore[arg-type]
        )


async def test_token_without_tenant_scope_is_rejected():
    token = create_access_token({"sub": "u", "tenant_id": "", "role": "viewer"})

    with pytest.raises(HTTPException) as excinfo:
        await get_current_tenant(token)

    assert excinfo.value.status_code == 403


async def test_token_with_tenant_scope_is_accepted():
    token = create_access_token({"sub": "u", "tenant_id": TENANT, "role": "viewer"})

    tenant = await get_current_tenant(token)

    assert tenant.tenant_id == TENANT
