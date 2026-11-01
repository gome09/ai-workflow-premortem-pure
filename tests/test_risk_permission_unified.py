# tests/test_risk_permission_unified.py
"""风险等级变更入口的统一权限校验。

覆盖：
- editor 通过六因子修改降低 effective tier 被拒绝（不能绕过 override 的 admin 门槛）；
- editor 升高风险、admin 降低风险正常；
- sensitive_personal 的确定性 floor 仍然生效；
- 风险因子变化会使旧 override 失效（版本绑定）；
- API 层 editor 降级 403 / admin 降级 200。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.risk.assessment import RiskOverridePermissionError
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


@pytest.fixture
def service(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "risk_permission.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService()


_LOW = {
    "impact": 0,
    "autonomy": 0,
    "data_sensitivity": 0,
    "reversibility": 0,
    "scale": 0,
    "external_exposure": 0,
}
_HIGH = {
    "impact": 2,
    "autonomy": 2,
    "data_sensitivity": 1,
    "reversibility": 1,
    "scale": 1,
    "external_exposure": 1,
}
_CRITICAL = {
    "impact": 2,
    "autonomy": 2,
    "data_sensitivity": 2,
    "reversibility": 2,
    "scale": 1,
    "external_exposure": 1,
}


def _risk_event(session, event_type: str):
    return [event for event in session.audit_events if event.event_type == event_type][-1]


def test_editor_cannot_lower_effective_tier_via_factors(service):
    ctx = service.create_session(tenant_id="tenant-a")
    assert service.get_risk_profile(ctx.session_id, tenant_id="tenant-a")["effective_tier"] == (
        "medium"
    )

    with pytest.raises(RiskOverridePermissionError):
        service.set_risk_profile(
            ctx.session_id,
            **_LOW,
            rationale="editor downgrade attempt",
            actor="alice",
            actor_role="editor",
            tenant_id="tenant-a",
        )

    stored = service.get_session(ctx.session_id, tenant_id="tenant-a")
    assert stored is not None
    assert stored.risk_profile is None
    assert not any(event.event_type == "risk_profile_updated" for event in stored.audit_events)


def test_editor_can_raise_risk_with_audit(service):
    ctx = service.create_session(tenant_id="tenant-a")
    result = service.set_risk_profile(
        ctx.session_id,
        **_HIGH,
        rationale="editor upgrades risk",
        actor="alice",
        actor_role="editor",
        tenant_id="tenant-a",
    )
    assert result["effective_tier"] == "high"

    stored = service.get_session(ctx.session_id, tenant_id="tenant-a")
    assert stored is not None
    event = _risk_event(stored, "risk_profile_updated")
    assert event.metadata["actor_role"] == "editor"
    assert event.metadata["is_downgrade"] is False
    assert event.metadata["before_effective_tier"] == "medium"
    assert event.metadata["after_effective_tier"] == "high"


def test_admin_can_lower_risk_with_downgrade_audit(service):
    ctx = service.create_session(tenant_id="tenant-a")
    service.set_risk_profile(
        ctx.session_id,
        **_HIGH,
        rationale="initial high",
        actor="alice",
        actor_role="editor",
        tenant_id="tenant-a",
    )
    result = service.set_risk_profile(
        ctx.session_id,
        **_LOW,
        rationale="admin downgrade",
        actor="root",
        actor_role="admin",
        tenant_id="tenant-a",
    )
    assert result["effective_tier"] == "low"

    stored = service.get_session(ctx.session_id, tenant_id="tenant-a")
    assert stored is not None
    event = _risk_event(stored, "risk_profile_updated")
    assert event.metadata["is_downgrade"] is True
    assert event.metadata["downgrade_authorized_by"] == "admin"
    assert event.metadata["before_effective_tier"] == "high"
    assert event.metadata["after_effective_tier"] == "low"
    assert event.metadata["factors_digest"]


def test_sensitive_personal_floor_blocks_editor_lowering(service):
    ctx = service.create_session(tenant_id="tenant-a")
    service.update_data_classification(
        ctx.session_id,
        data_classification="sensitive_personal",
        note="contains personal data",
        actor_role="admin",
        tenant_id="tenant-a",
    )
    assert service.get_risk_profile(ctx.session_id, tenant_id="tenant-a")["effective_tier"] == (
        "critical"
    )

    with pytest.raises(RiskOverridePermissionError):
        service.set_risk_profile(
            ctx.session_id,
            **_LOW,
            rationale="editor tries to clear factors",
            actor="alice",
            actor_role="editor",
            tenant_id="tenant-a",
        )

    result = service.set_risk_profile(
        ctx.session_id,
        **_LOW,
        rationale="admin clears factors; floor stays high",
        actor="root",
        actor_role="admin",
        tenant_id="tenant-a",
    )
    assert result["effective_tier"] == "high"
    assert result["floor_tier"] == "high"

    with pytest.raises(RiskOverridePermissionError):
        service.override_risk_tier(
            ctx.session_id,
            requested_tier="medium",
            reason="editor tries to drop below floor",
            actor="alice",
            actor_role="editor",
            tenant_id="tenant-a",
        )


def test_override_is_invalidated_after_risk_inputs_change(service):
    ctx = service.create_session(tenant_id="tenant-a")
    service.set_risk_profile(
        ctx.session_id,
        **_LOW,
        rationale="low baseline",
        actor="root",
        actor_role="admin",
        tenant_id="tenant-a",
    )
    service.override_risk_tier(
        ctx.session_id,
        requested_tier="high",
        reason="admin raises tier",
        actor="root",
        actor_role="admin",
        tenant_id="tenant-a",
    )
    assert service.get_risk_profile(ctx.session_id, tenant_id="tenant-a")["effective_tier"] == (
        "high"
    )

    result = service.set_risk_profile(
        ctx.session_id,
        **_CRITICAL,
        rationale="new critical factors",
        actor="alice",
        actor_role="editor",
        tenant_id="tenant-a",
    )
    assert result["effective_tier"] == "critical"
    assert result["override"]["effective_tier"] == "high"
    assert any("invalidated because risk inputs changed" in reason for reason in result["reasons"])

    stored = service.get_session(ctx.session_id, tenant_id="tenant-a")
    assert stored is not None
    event = _risk_event(stored, "risk_profile_updated")
    assert event.metadata["after_effective_tier"] == "critical"


@pytest.fixture
def api_client(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("psycopg")
    pytest.importorskip("redis")
    pytest.importorskip("langchain_core")
    pytest.importorskip("langchain_openai")
    pytest.importorskip("tavily")
    pytest.importorskip("prometheus_fastapi_instrumentator")

    from fastapi.testclient import TestClient

    store = SQLiteSessionStore(str(tmp_path / "risk_permission_api.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        from api.main import app

        yield TestClient(app)


def _headers(role: str, tenant_id: str = "test-tenant") -> dict:
    from auth.jwt import create_access_token

    token = create_access_token({"sub": f"{role}-user", "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


def test_api_editor_downgrade_returns_403(api_client):
    created = api_client.post("/sessions/", json={}, headers=_headers("editor")).json()
    session_id = created["session_id"]

    response = api_client.put(
        f"/sessions/{session_id}/risk-profile", json=_LOW, headers=_headers("editor")
    )
    assert response.status_code == 403
    stored = api_client.get(f"/sessions/{session_id}/risk-profile", headers=_headers("editor"))
    assert stored.json()["effective_tier"] == "medium"
    assert stored.json()["source"] == "legacy_inference"


def test_api_admin_downgrade_returns_200(api_client):
    created = api_client.post("/sessions/", json={}, headers=_headers("admin")).json()
    session_id = created["session_id"]

    response = api_client.put(
        f"/sessions/{session_id}/risk-profile", json=_LOW, headers=_headers("admin")
    )
    assert response.status_code == 200
    assert response.json()["effective_tier"] == "low"
    assert response.json()["source"] == "human"
