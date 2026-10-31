# tests/test_risk_profile_api.py
"""Milestone 2: risk-profile API contract and role boundaries."""

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
from storage.backends.sqlite_store import SQLiteSessionStore


@pytest.fixture
def client_and_service(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "risk_api.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        from api.main import app

        yield TestClient(app), SessionService()


def _headers(role: str, tenant_id: str = "test-tenant") -> dict:
    token = create_access_token({"sub": f"{role}-user", "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


_LOW = {
    "impact": 0,
    "autonomy": 0,
    "data_sensitivity": 0,
    "reversibility": 0,
    "scale": 0,
    "external_exposure": 0,
    "rationale": "low baseline",
}


def test_get_put_and_override_profile(client_and_service):
    client, service = client_and_service
    created = client.post("/sessions/", json={}, headers=_headers("editor")).json()
    session_id = created["session_id"]

    response = client.get(f"/sessions/{session_id}/risk-profile", headers=_headers("viewer"))
    assert response.status_code == 200
    assert response.json()["session_id"] == session_id

    response = client.put(
        f"/sessions/{session_id}/risk-profile", json=_LOW, headers=_headers("editor")
    )
    assert response.status_code == 200
    assert response.json()["effective_tier"] == "low"
    assert response.json()["source"] == "human"

    response = client.post(
        f"/sessions/{session_id}/risk-profile/override",
        json={"requested_tier": "high", "reason": "对外发布"},
        headers=_headers("editor"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["effective_tier"] == "high"
    assert body["override"]["requested_tier"] == "high"

    stored = service.get_session(session_id, tenant_id="test-tenant")
    assert stored is not None
    event = next(e for e in stored.audit_events if e.event_type == "risk_tier_overridden")
    assert event.metadata["actor"] == "editor-user"
    assert event.metadata["tenant_id"] == "test-tenant"


def test_editor_downgrade_returns_403(client_and_service):
    client, _service = client_and_service
    created = client.post("/sessions/", json={}, headers=_headers("editor")).json()
    session_id = created["session_id"]
    client.put(
        f"/sessions/{session_id}/risk-profile",
        json={
            **_LOW,
            "impact": 1,
            "autonomy": 2,
            "data_sensitivity": 1,
            "reversibility": 1,
            "scale": 1,
            "external_exposure": 1,
        },
        headers=_headers("editor"),
    )
    response = client.post(
        f"/sessions/{session_id}/risk-profile/override",
        json={"requested_tier": "medium", "reason": "edit 尝试"},
        headers=_headers("editor"),
    )
    assert response.status_code == 403


def test_admin_downgrade_succeeds(client_and_service):
    client, _service = client_and_service
    created = client.post("/sessions/", json={}, headers=_headers("admin")).json()
    session_id = created["session_id"]
    client.put(
        f"/sessions/{session_id}/risk-profile",
        json={
            **_LOW,
            "impact": 1,
            "autonomy": 2,
            "data_sensitivity": 1,
            "reversibility": 1,
            "scale": 1,
            "external_exposure": 1,
        },
        headers=_headers("admin"),
    )
    response = client.post(
        f"/sessions/{session_id}/risk-profile/override",
        json={"requested_tier": "medium", "reason": "admin 复核"},
        headers=_headers("admin"),
    )
    assert response.status_code == 200
    assert response.json()["effective_tier"] == "medium"


def test_invalid_factor_returns_422(client_and_service):
    client, _service = client_and_service
    created = client.post("/sessions/", json={}, headers=_headers("editor")).json()
    response = client.put(
        f"/sessions/{created['session_id']}/risk-profile",
        json={**_LOW, "impact": 4},
        headers=_headers("editor"),
    )
    assert response.status_code == 422


def test_cross_tenant_profile_returns_404(client_and_service):
    client, _service = client_and_service
    created = client.post("/sessions/", json={}, headers=_headers("editor")).json()
    response = client.get(
        f"/sessions/{created['session_id']}/risk-profile",
        headers=_headers("editor", tenant_id="other-tenant"),
    )
    assert response.status_code == 404
    response = client.post(
        f"/sessions/{created['session_id']}/risk-profile/override",
        json={"requested_tier": "high", "reason": "cross tenant"},
        headers=_headers("admin", tenant_id="other-tenant"),
    )
    assert response.status_code == 404
