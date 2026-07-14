# tests/test_session_lifecycle.py
"""T1.6 数据生命周期最小集 (session lifecycle) tests.

Covers:
- DELETE /sessions/{id} non-admin → 403
- DELETE /sessions/{id} non-existent → 404
- DELETE /sessions/{id} existing admin → 200 + summary
- GET /sessions/{id} after DELETE → 404
- audit_events_archive contains original events + 1 session_purged event
- /health exposes audit_retention_days / session_retention_days
"""

from __future__ import annotations

import sqlite3
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
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


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

        yield TestClient(app), SessionService(), str(db_path)


def _headers(role: str) -> dict:
    token = create_access_token({"sub": "test-user", "tenant_id": "test-tenant", "role": role})
    return {"Authorization": f"Bearer {token}"}


# ── 1: DELETE non-admin returns 403 ───────────────────────────────────
def test_delete_non_admin_returns_403(client_and_service):
    client, service, _ = client_and_service
    ctx = service.create_session(tenant_id="test-tenant")

    response = client.delete(f"/sessions/{ctx.session_id}", headers=_headers("editor"))
    assert response.status_code == 403


# ── 2: DELETE non-existent session returns 404 ────────────────────────
def test_delete_non_existent_returns_404(client_and_service):
    client, _, _ = client_and_service

    response = client.delete("/sessions/non-existent-session", headers=_headers("admin"))
    assert response.status_code == 404


# ── 3: DELETE existing session succeeds ───────────────────────────────
def test_delete_existing_session_succeeds(client_and_service):
    client, service, _ = client_and_service
    ctx = service.create_session(tenant_id="test-tenant")

    response = client.delete(f"/sessions/{ctx.session_id}", headers=_headers("admin"))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["session_id"] == ctx.session_id
    assert "archived_audit_events" in data
    assert data["archived_audit_events"] >= 1
    assert data["purged_by"] == "test-user"


# ── 4: Session not retrievable after DELETE ───────────────────────────
def test_session_not_retrievable_after_delete(client_and_service):
    client, service, _ = client_and_service
    ctx = service.create_session(tenant_id="test-tenant")

    delete_resp = client.delete(f"/sessions/{ctx.session_id}", headers=_headers("admin"))
    assert delete_resp.status_code == 200

    get_resp = client.get(f"/sessions/{ctx.session_id}", headers=_headers("admin"))
    assert get_resp.status_code == 404


# ── 5: Audit events archived ──────────────────────────────────────────
def test_audit_events_archived_after_delete(client_and_service):
    client, service, db_path = client_and_service
    ctx = service.create_session(tenant_id="test-tenant")

    # Create an audit event via PATCH upgrade (append_audit_event + save)
    patch_resp = client.patch(
        f"/sessions/{ctx.session_id}/data-classification",
        json={"data_classification": "sensitive_personal", "note": "upgrade for archive test"},
        headers=_headers("editor"),
    )
    assert patch_resp.status_code == 200

    # DELETE the session — should archive existing audit events + write session_purged
    delete_resp = client.delete(f"/sessions/{ctx.session_id}", headers=_headers("admin"))
    assert delete_resp.status_code == 200
    assert delete_resp.json()["archived_audit_events"] >= 2  # 1 original + 1 purge

    # Query the archive table directly
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT event_type FROM audit_events_archive WHERE original_session_id = ?",
        (ctx.session_id,),
    ).fetchall()
    conn.close()

    event_types = [r["event_type"] for r in rows]
    # Original event (data_classification_changed) + session_purged
    assert "data_classification_changed" in event_types
    assert "session_purged" in event_types
    assert len(rows) >= 2


# ── 6: /health exposes retention config ───────────────────────────────
def test_health_exposes_retention_config():
    from api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "audit_retention_days" in data
    assert "session_retention_days" in data
    assert isinstance(data["audit_retention_days"], int)
    assert isinstance(data["session_retention_days"], int)
