# tests/test_risk_override_service.py
"""Milestone 2: human risk override audit and tenant isolation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.risk.assessment import RiskOverridePermissionError
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


@pytest.fixture
def service(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "risk.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService()


def _low_factors(**overrides):
    values = {
        "impact": 0,
        "autonomy": 0,
        "data_sensitivity": 0,
        "reversibility": 0,
        "scale": 0,
        "external_exposure": 0,
    }
    values.update(overrides)
    return values


def test_set_profile_and_read_back(service):
    ctx = service.create_session(tenant_id="tenant-a")
    result = service.set_risk_profile(
        ctx.session_id,
        **_low_factors(),
        rationale="initial factors",
        actor="alice",
        actor_role="editor",
        tenant_id="tenant-a",
    )
    assert result["effective_tier"] == "low"
    assert result["source"] == "human"
    assert service.get_risk_profile(ctx.session_id, tenant_id="tenant-a")["effective_tier"] == "low"

    stored = service.get_session(ctx.session_id, tenant_id="tenant-a")
    assert stored is not None
    assert any(event.event_type == "risk_profile_updated" for event in stored.audit_events)


def test_override_upgrade_records_full_audit(service):
    ctx = service.create_session(tenant_id="tenant-a")
    service.set_risk_profile(
        ctx.session_id, **_low_factors(), actor="alice", actor_role="editor", tenant_id="tenant-a"
    )
    result = service.override_risk_tier(
        ctx.session_id,
        requested_tier="high",
        reason="对外发布前复核",
        actor="alice",
        actor_role="editor",
        tenant_id="tenant-a",
    )
    assert result["effective_tier"] == "high"
    assert result["override"]["original_tier"] == "low"
    assert result["override"]["requested_tier"] == "high"
    assert result["override"]["effective_tier"] == "high"
    assert result["override"]["tenant_id"] == "tenant-a"

    stored = service.get_session(ctx.session_id, tenant_id="tenant-a")
    assert stored is not None
    events = [event for event in stored.audit_events if event.event_type == "risk_tier_overridden"]
    assert events
    metadata = events[-1].metadata
    assert metadata["original_tier"] == "low"
    assert metadata["requested_tier"] == "high"
    assert metadata["effective_tier"] == "high"
    assert metadata["reason"] == "对外发布前复核"
    assert metadata["actor"] == "alice"
    assert metadata["actor_role"] == "editor"
    assert metadata["tenant_id"] == "tenant-a"


def test_non_admin_downgrade_is_rejected(service):
    ctx = service.create_session(tenant_id="tenant-a")
    service.set_risk_profile(
        ctx.session_id,
        **_low_factors(
            impact=1, autonomy=2, data_sensitivity=1, reversibility=1, scale=1, external_exposure=1
        ),
        actor="alice",
        actor_role="editor",
        tenant_id="tenant-a",
    )
    assert (
        service.get_risk_profile(ctx.session_id, tenant_id="tenant-a")["effective_tier"] == "high"
    )
    with pytest.raises(RiskOverridePermissionError):
        service.override_risk_tier(
            ctx.session_id,
            requested_tier="medium",
            reason="普通编辑尝试降级",
            actor="bob",
            actor_role="editor",
            tenant_id="tenant-a",
        )


def test_admin_downgrade_above_floor_is_allowed(service):
    ctx = service.create_session(tenant_id="tenant-a")
    service.set_risk_profile(
        ctx.session_id,
        **_low_factors(
            impact=1, autonomy=2, data_sensitivity=1, reversibility=1, scale=1, external_exposure=1
        ),
        actor="alice",
        actor_role="editor",
        tenant_id="tenant-a",
    )
    result = service.override_risk_tier(
        ctx.session_id,
        requested_tier="medium",
        reason="管理员复核后下调",
        actor="admin",
        actor_role="admin",
        tenant_id="tenant-a",
    )
    assert result["effective_tier"] == "medium"
    assert result["override"]["floor_tier"] == "low"


def test_downgrade_below_floor_is_clamped(service):
    ctx = service.create_session(tenant_id="tenant-a")
    service.update_data_classification(
        ctx.session_id,
        data_classification="sensitive_personal",
        note="包含个人信息",
        actor_role="admin",
        tenant_id="tenant-a",
    )
    service.set_risk_profile(
        ctx.session_id, **_low_factors(), actor="alice", actor_role="editor", tenant_id="tenant-a"
    )
    assert (
        service.get_risk_profile(ctx.session_id, tenant_id="tenant-a")["effective_tier"] == "high"
    )

    result = service.override_risk_tier(
        ctx.session_id,
        requested_tier="low",
        reason="数据已脱敏",
        actor="admin",
        actor_role="admin",
        tenant_id="tenant-a",
    )
    assert result["override"]["requested_tier"] == "low"
    assert result["override"]["floor_tier"] == "high"
    assert result["effective_tier"] == "high"


def test_cross_tenant_profile_access_is_not_found(service):
    ctx = service.create_session(tenant_id="tenant-a")
    service.set_risk_profile(
        ctx.session_id, **_low_factors(), actor="alice", actor_role="editor", tenant_id="tenant-a"
    )
    with pytest.raises(ValueError, match="Session not found"):
        service.get_risk_profile(ctx.session_id, tenant_id="tenant-b")
    with pytest.raises(ValueError, match="Session not found"):
        service.override_risk_tier(
            ctx.session_id,
            requested_tier="high",
            reason="cross tenant attempt",
            actor="mallory",
            actor_role="admin",
            tenant_id="tenant-b",
        )
