# tests/test_data_classification.py
"""T1.1 数据分类分级 (data_classification) tests.

Covers:
- Scenario sessions default to 'public_demo', user sessions to 'business_internal'.
- PATCH upgrade/same-level allowed for editor+.
- PATCH downgrade requires admin (editor -> 403), admin -> 200.
- Downgrade produces an AuditEvent with metadata.is_downgrade=True.
- v0.7.0 -> v0.8.0 migration backfills data_classification.
"""

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
from core.config import settings
from core.migrations import migrate_context
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


# ── Service-level fixtures (direct SessionService usage) ──────────────
@pytest.fixture
def isolated_service(tmp_path):
    db_path = tmp_path / "workflow.db"
    store = SQLiteSessionStore(str(db_path))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService()


# ── API-level fixtures (TestClient + shared store/cache) ──────────────
@pytest.fixture
def client_and_service(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "default_scenario_id", "")
    db_path = tmp_path / "workflow.db"
    store = SQLiteSessionStore(str(db_path))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
        patch("api.routers.session.session_store", store),
        patch("api.routers.session.context_cache", cache),
    ):
        from api.main import app

        yield TestClient(app), SessionService()


def _headers(role: str) -> dict:
    token = create_access_token({"sub": "test-user", "tenant_id": "test-tenant", "role": role})
    return {"Authorization": f"Bearer {token}"}


def _set_classification(client, session_id: str, value: str, role: str = "admin") -> None:
    """Helper: upgrade session to `value` via the PATCH endpoint (admin by default)."""
    response = client.patch(
        f"/sessions/{session_id}/data-classification",
        json={"data_classification": value, "note": "setup"},
        headers=_headers(role),
    )
    assert response.status_code == 200, response.text


# ── 1 & 2: create_session defaults ────────────────────────────────────
def test_scenario_session_gets_public_demo(monkeypatch, isolated_service):
    monkeypatch.setattr(settings, "default_scenario_id", "")
    ctx = isolated_service.create_session(scenario_id="generic_rag_demo")
    assert ctx.selected_scenario_id == "generic_rag_demo"
    assert ctx.data_classification == "public_demo"


def test_user_session_gets_business_internal(monkeypatch, isolated_service):
    monkeypatch.setattr(settings, "default_scenario_id", "")
    ctx = isolated_service.create_session()
    assert ctx.selected_scenario_id is None
    assert ctx.data_classification == "business_internal"


# ── 3: PATCH upgrade works for editor ─────────────────────────────────
def test_patch_upgrade_works_for_editor(client_and_service):
    client, service = client_and_service
    ctx = service.create_session(tenant_id="test-tenant")
    assert ctx.data_classification == "business_internal"

    response = client.patch(
        f"/sessions/{ctx.session_id}/data-classification",
        json={"data_classification": "sensitive_personal", "note": "upgrade"},
        headers=_headers("editor"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["before"] == "business_internal"
    assert data["after"] == "sensitive_personal"
    assert data["is_downgrade"] is False


# ── 4: PATCH downgrade requires admin (editor -> 403) ─────────────────
def test_patch_downgrade_requires_admin(client_and_service):
    client, service = client_and_service
    ctx = service.create_session(tenant_id="test-tenant")
    # Upgrade to sensitive_personal first (admin), then attempt downgrade as editor.
    _set_classification(client, ctx.session_id, "sensitive_personal", role="admin")

    response = client.patch(
        f"/sessions/{ctx.session_id}/data-classification",
        json={"data_classification": "business_internal", "note": "downgrade attempt"},
        headers=_headers("editor"),
    )
    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


# ── 5: PATCH downgrade works for admin ────────────────────────────────
def test_patch_downgrade_works_for_admin(client_and_service):
    client, service = client_and_service
    ctx = service.create_session(tenant_id="test-tenant")
    _set_classification(client, ctx.session_id, "sensitive_personal", role="admin")

    response = client.patch(
        f"/sessions/{ctx.session_id}/data-classification",
        json={"data_classification": "business_internal", "note": "admin downgrade"},
        headers=_headers("admin"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["after"] == "business_internal"
    assert data["is_downgrade"] is True


# ── 6: Downgrade produces AuditEvent ──────────────────────────────────
def test_downgrade_produces_audit_event(client_and_service):
    client, service = client_and_service
    ctx = service.create_session(tenant_id="test-tenant")
    _set_classification(client, ctx.session_id, "sensitive_personal", role="admin")

    response = client.patch(
        f"/sessions/{ctx.session_id}/data-classification",
        json={"data_classification": "public_demo", "note": "audit check"},
        headers=_headers("admin"),
    )
    assert response.status_code == 200

    refreshed = service.get_session(ctx.session_id, tenant_id="test-tenant")
    assert refreshed is not None
    downgrade_events = [
        e
        for e in refreshed.audit_events
        if e.event_type == "data_classification_changed" and e.metadata.get("is_downgrade") is True
    ]
    assert downgrade_events, "expected a downgrade audit event"
    event = downgrade_events[-1]
    assert event.before_snapshot == {"data_classification": "sensitive_personal"}
    assert event.after_snapshot == {"data_classification": "public_demo"}


# ── 7: Migration v0.7.0 -> v0.8.0 ─────────────────────────────────────
def test_migration_v070_to_v080_backfills_business_internal():
    raw = {
        "context_schema_version": "0.7.0",
        "session_id": "test-session",
        "selected_scenario_id": None,
    }
    ctx = migrate_context(raw)
    assert ctx.context_schema_version == "0.8.0"
    assert ctx.data_classification == "business_internal"


def test_migration_v070_to_v080_backfills_public_demo_for_scenario():
    raw = {
        "context_schema_version": "0.7.0",
        "session_id": "test-session",
        "selected_scenario_id": "generic_rag_demo",
    }
    ctx = migrate_context(raw)
    assert ctx.context_schema_version == "0.8.0"
    assert ctx.data_classification == "public_demo"


def test_migration_v070_to_v080_records_history():
    raw = {"context_schema_version": "0.7.0", "session_id": "test-session"}
    ctx = migrate_context(raw)
    assert ctx.migration_history
    last = ctx.migration_history[-1]
    assert last.from_version == "0.7.0"
    assert last.to_version == "0.8.0"
