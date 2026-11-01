# tests/test_expert_review_approval.py
"""CRITICAL expert-review approval identity, authorization, and version binding.

覆盖：
- editor 无资质批准被拒绝；
- 会话创建者自审批被拒绝；
- 旧会话缺少 created_by 时 fail-closed；
- 风险输入变化后旧批准被判定过期；
- admin 独立批准成功后 gate 不再阻断，且审计含身份与摘要；
- API 403 / 409 / 跨租户 404 回归。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.gates.rules.expert_review import ExpertReviewRule
from core.governance.action_resolution import resolve_action, resolve_action_with_result
from core.governance.expert_review import (
    ExpertReviewAuthorizationError,
)
from core.models import ProjectContext
from core.risk.models import RiskFactorScores
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "test-tenant"
_CREATOR = "creator-user"
_REVIEWER = "reviewer-admin"

_CRITICAL = RiskFactorScores(
    impact=2,
    autonomy=2,
    data_sensitivity=2,
    reversibility=2,
    scale=1,
    external_exposure=1,
    rationale="critical medication workflow",
    source="human",
)


def _critical_ctx(created_by: str = _CREATOR, tenant_id: str = _TENANT) -> ProjectContext:
    ctx = ProjectContext(
        research_target="药物管理系统",
        tenant_id=tenant_id,
        created_by=created_by,
    )
    ctx.risk_profile = _CRITICAL
    ExpertReviewRule().evaluate(ctx, 3)
    return ctx


def _expert_action(ctx: ProjectContext):
    return next(action for action in ctx.pending_actions if action.source_type == "expert_review")


def test_editor_cannot_approve_expert_review():
    ctx = _critical_ctx()
    action = _expert_action(ctx)

    with pytest.raises(ExpertReviewAuthorizationError, match="admin role"):
        resolve_action(
            ctx,
            action_id=action.action_id,
            decision="approve",
            actor_id="editor-user",
            actor_role="editor",
        )

    assert action.status == "pending"
    assert "admin role" in (action.last_resolution_error or "")


def test_session_creator_cannot_self_approve():
    ctx = _critical_ctx(created_by=_CREATOR)
    action = _expert_action(ctx)

    with pytest.raises(ExpertReviewAuthorizationError, match="Self-approval"):
        resolve_action(
            ctx,
            action_id=action.action_id,
            decision="approve",
            actor_id=_CREATOR,
            actor_role="admin",
        )

    assert action.status == "pending"


def test_missing_creator_fails_closed():
    ctx = _critical_ctx(created_by="")
    action = _expert_action(ctx)

    with pytest.raises(ExpertReviewAuthorizationError, match="creator is not recorded"):
        resolve_action(
            ctx,
            action_id=action.action_id,
            decision="approve",
            actor_id=_REVIEWER,
            actor_role="admin",
        )

    assert action.status == "pending"


def test_changed_risk_inputs_make_approval_stale():
    ctx = _critical_ctx()
    action = _expert_action(ctx)
    original_digest = action.payload_before["risk_assessment_digest"]
    assert original_digest

    ctx.risk_profile = RiskFactorScores(
        impact=3,
        autonomy=2,
        data_sensitivity=2,
        reversibility=2,
        scale=1,
        external_exposure=1,
        rationale="critical factors changed",
        source="human",
    )

    result = resolve_action_with_result(
        ctx,
        action_id=action.action_id,
        decision="approve",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert result.result_status == "stale"
    assert "changed" in (result.error_message or "")
    assert action.status == "pending"


def test_valid_admin_approval_records_audit_and_unblocks():
    ctx = _critical_ctx()
    action = _expert_action(ctx)

    resolved = resolve_action(
        ctx,
        action_id=action.action_id,
        decision="approve",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert resolved.status == "resolved"
    assert resolved.reviewer_decision == "approve"

    event = next(
        event for event in reversed(ctx.audit_events) if event.event_type == "human_action_resolved"
    )
    assert event.metadata["reviewer_id"] == _REVIEWER
    assert event.metadata["reviewer_role"] == "admin"
    assert event.metadata["expert_review_approved"] is True
    assert (
        event.metadata["risk_assessment_digest"] == action.payload_before["risk_assessment_digest"]
    )

    blockers = ExpertReviewRule().evaluate(ctx, 3)
    assert blockers == []


def test_risk_increase_after_approval_requires_new_review():
    ctx = _critical_ctx()
    action = _expert_action(ctx)
    resolve_action(
        ctx,
        action_id=action.action_id,
        decision="approve",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert ExpertReviewRule().evaluate(ctx, 3) == []

    ctx.risk_profile = RiskFactorScores(
        impact=3,
        autonomy=3,
        data_sensitivity=3,
        reversibility=3,
        scale=1,
        external_exposure=2,
        rationale="risk increased after approval",
        source="human",
    )
    blockers = ExpertReviewRule().evaluate(ctx, 3)
    assert len(blockers) == 1
    assert blockers[0].rule_id == "expert_review"
    new_action = next(
        action
        for action in ctx.pending_actions
        if action.source_type == "expert_review" and action.status == "pending"
    )
    assert (
        new_action.payload_before["risk_assessment_digest"]
        != action.payload_before["risk_assessment_digest"]
    )


@pytest.fixture
def api_client_and_store(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("psycopg")
    pytest.importorskip("redis")
    pytest.importorskip("langchain_core")
    pytest.importorskip("langchain_openai")
    pytest.importorskip("tavily")
    pytest.importorskip("prometheus_fastapi_instrumentator")

    from fastapi.testclient import TestClient

    store = SQLiteSessionStore(str(tmp_path / "expert_review_api.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("storage.session_store.session_store", store),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        from api.main import app

        yield TestClient(app), store


def _headers(role: str, sub: str, tenant_id: str = _TENANT) -> dict:
    from auth.jwt import create_access_token

    token = create_access_token({"sub": sub, "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


def test_api_rejects_unqualified_self_and_cross_tenant_then_allows_admin(
    api_client_and_store,
):
    client, store = api_client_and_store
    ctx = _critical_ctx()
    action = _expert_action(ctx)
    store.save(ctx)

    base = f"/sessions/{ctx.session_id}/actions/{action.action_id}/resolve"

    response = client.post(
        base,
        json={"decision": "approve", "note": "editor attempt"},
        headers=_headers("editor", "editor-user"),
    )
    assert response.status_code == 403

    response = client.post(
        base,
        json={"decision": "approve", "note": "self approval"},
        headers=_headers("admin", _CREATOR),
    )
    assert response.status_code == 403

    response = client.post(
        base,
        json={"decision": "approve", "note": "cross tenant"},
        headers=_headers("admin", "other-admin", tenant_id="other-tenant"),
    )
    assert response.status_code == 404

    response = client.post(
        base,
        json={"decision": "approve", "note": "independent expert approval"},
        headers=_headers("admin", _REVIEWER),
    )
    assert response.status_code == 200
    assert response.json()["result_status"] == "resolved"

    reloaded = store.load(ctx.session_id, _TENANT)
    assert reloaded is not None
    resolved = next(item for item in reloaded.pending_actions if item.action_id == action.action_id)
    assert resolved.status == "resolved"
    assert resolved.reviewer_decision == "approve"
