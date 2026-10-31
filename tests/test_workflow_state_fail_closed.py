# tests/test_workflow_state_fail_closed.py
"""Milestone 1 P1: 未知/非法 workflow state 必须 fail-closed。

验收：
- 未知状态不执行任何节点、不回退 INIT，进入 RECOVERY_REQUIRED 并写审计。
- ERROR / RECOVERY_REQUIRED 下 runner 不执行节点，send_message 抛
  WorkflowBlockedError，API 返回 409 + recovery_endpoint。
- 阻断态没有可推进阶段（current_stage_id == 0 / actionable_stage_ids == []），
  stage advancement coordinator 明确给出 workflow_state_blocked。
- 恢复端点只接受合法目标状态：不存在 404 / 未阻断 409 / 非法目标 400。
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from auth.jwt import create_access_token
from core.models import ProjectContext, SessionState
from core.session_service import SessionService
from core.stage_advancement_coordinator import advance_stage_if_ready
from core.stage_scope_service import actionable_stage_ids, current_stage_id
from core.workflow_state_service import (
    WorkflowBlockedError,
    assert_advanceable,
    recover_workflow,
)
from graph.runner import run_one_step
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


# ── fixtures ──────────────────────────────────────────────────────────
@pytest.fixture
def store(tmp_path):
    backend = SQLiteSessionStore(db_path=str(tmp_path / "workflow_state.db"))
    backend.initialize()
    return backend


@pytest.fixture
def isolated_service(store):
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService(), store, cache


@pytest.fixture
def api_client(store):
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        from api.main import app

        yield TestClient(app), store, cache


def _headers(role: str = "admin") -> dict:
    token = create_access_token({"sub": "test-user", "tenant_id": "test-tenant", "role": role})
    return {"Authorization": f"Bearer {token}"}


def _blocked_ctx(state: SessionState = SessionState.RECOVERY_REQUIRED) -> ProjectContext:
    ctx = ProjectContext()
    ctx.current_state = state
    ctx.last_error = "simulated invalid state"
    ctx.pending_input = "继续推进"
    return ctx


# ── 1. runner: unknown state never falls back to INIT ────────────────
def test_unknown_state_enters_recovery_required_without_init_fallback():
    ctx = ProjectContext()
    ctx.current_state = "corrupted_by_manual_db_edit"  # type: ignore[assignment]
    ctx.pending_input = "继续"

    init_node = Mock(side_effect=AssertionError("INIT node must not run"))
    with patch.dict("graph.runner.NODE_BY_STATE", {SessionState.INIT: init_node}, clear=True):
        updated = run_one_step(ctx)

    init_node.assert_not_called()
    assert updated.current_state == SessionState.RECOVERY_REQUIRED
    assert "invalid workflow state" in updated.last_error
    assert updated.pending_input == ""
    assert "workflow_state_invalid" in [event.event_type for event in updated.audit_events]


def test_known_state_without_registered_node_fails_closed():
    ctx = ProjectContext()
    ctx.current_state = SessionState.ITERATING  # 已知状态但无单步节点

    # 清空注册表模拟"状态已知但没有节点实现"，仍必须 fail-closed。
    with patch.dict("graph.runner.NODE_BY_STATE", {}, clear=True):
        updated = run_one_step(ctx)

    assert updated.current_state == SessionState.RECOVERY_REQUIRED


@pytest.mark.parametrize("blocked_state", [SessionState.ERROR, SessionState.RECOVERY_REQUIRED])
def test_blocked_states_never_execute_nodes(blocked_state):
    ctx = _blocked_ctx(blocked_state)
    node = Mock(side_effect=AssertionError("blocked state must not execute a node"))
    with patch.dict("graph.runner.NODE_BY_STATE", {blocked_state: node}, clear=True):
        updated = run_one_step(ctx)

    node.assert_not_called()
    assert updated.current_state == blocked_state
    assert updated.pending_input == ""
    assert "workflow_advancement_blocked" in [event.event_type for event in updated.audit_events]


# ── 2. assert_advanceable / send_message ─────────────────────────────
@pytest.mark.parametrize(
    "state",
    [SessionState.ERROR, SessionState.RECOVERY_REQUIRED, "not_a_real_state"],
)
def test_assert_advanceable_rejects_blocked_and_unknown_states(state):
    ctx = ProjectContext()
    ctx.current_state = state  # type: ignore[assignment]
    ctx.last_error = "gpu failure"

    with pytest.raises(WorkflowBlockedError) as exc:
        assert_advanceable(ctx)

    assert exc.value.state == getattr(state, "value", str(state))


@pytest.mark.parametrize(
    "state", [SessionState.INIT, SessionState.S1_RUNNING, SessionState.S4_REVIEW]
)
def test_assert_advanceable_allows_resumable_states(state):
    ctx = ProjectContext()
    ctx.current_state = state
    assert_advanceable(ctx)  # must not raise


def test_send_message_refuses_blocked_session(isolated_service):
    service, store, cache = isolated_service
    ctx = service.create_session(tenant_id="tenant-a")
    ctx.current_state = SessionState.ERROR
    ctx.last_error = "stage crashed"
    store.save(ctx)
    cache.set(ctx)

    with pytest.raises(WorkflowBlockedError):
        service.send_message(ctx.session_id, "继续推进", tenant_id="tenant-a")


def test_send_message_refuses_unknown_state_session(isolated_service):
    service, store, cache = isolated_service
    ctx = service.create_session(tenant_id="tenant-a")
    ctx.current_state = "legacy_state"  # type: ignore[assignment]
    store.save(ctx)
    # create_session 已把合法 INIT 快照写入缓存，必须先失效才能命中存储层清洗路径。
    cache.delete(ctx.session_id, "tenant-a")

    # 缓存中的非法状态无法通过校验，读取回退到存储层，并由存储层清洗为阻断态。
    with pytest.raises(WorkflowBlockedError) as exc:
        service.send_message(ctx.session_id, "继续推进", tenant_id="tenant-a")

    assert exc.value.state == SessionState.RECOVERY_REQUIRED.value
    assert "legacy_state" in exc.value.last_error


def test_persisted_unknown_state_loads_as_recovery_required(store):
    """存储层边界：历史库中的未知状态必须被清洗为 RECOVERY_REQUIRED。"""
    raw = {
        "session_id": "sess-legacy",
        "current_state": "unknown_legacy_state",
        "tenant_id": "tenant-a",
    }
    with store._get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, tenant_id, current_state, context_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "sess-legacy",
                "tenant-a",
                "unknown_legacy_state",
                json.dumps(raw),
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
        conn.commit()

    loaded = store.load("sess-legacy", "tenant-a")
    assert loaded is not None
    assert loaded.current_state == SessionState.RECOVERY_REQUIRED
    assert "unknown_legacy_state" in loaded.last_error


# ── 3. blocked states expose no actionable stage ─────────────────────
@pytest.mark.parametrize("blocked_state", [SessionState.ERROR, SessionState.RECOVERY_REQUIRED])
def test_blocked_state_has_no_actionable_stage(blocked_state, store):
    ctx = _blocked_ctx(blocked_state)
    assert current_stage_id(ctx) == 0
    assert actionable_stage_ids(ctx) == []

    with patch("storage.session_store.session_store", store):
        decision = advance_stage_if_ready(ctx, 1, reason="blocked-probe", source="api_advance")

    assert decision.can_advance is False
    assert decision.advanced is False
    assert decision.decision_reason == "workflow_state_blocked"


# ── 4. API: 409 + recovery endpoint ─────────────────────────────────
def _seed_blocked_session(store, cache, state: SessionState, tenant_id: str = "test-tenant"):
    ctx = ProjectContext(tenant_id=tenant_id, session_name="wf-state")
    ctx.current_state = state
    ctx.last_error = "simulated"
    store.save(ctx)
    cache.set(ctx)
    return ctx


@pytest.mark.parametrize("blocked_state", [SessionState.ERROR, SessionState.RECOVERY_REQUIRED])
def test_chat_returns_409_for_blocked_state(api_client, blocked_state):
    client, store, cache = api_client
    ctx = _seed_blocked_session(store, cache, blocked_state)

    response = client.post(
        f"/chat/{ctx.session_id}",
        json={"user_input": "继续推进"},
        headers=_headers("editor"),
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["state"] == blocked_state.value
    assert body["recovery_endpoint"].endswith(f"/sessions/{ctx.session_id}/workflow/recover")


def test_chat_returns_409_for_unknown_state(api_client):
    client, store, cache = api_client
    ctx = ProjectContext(tenant_id="test-tenant", session_name="wf-state")
    ctx.current_state = "legacy_state"  # type: ignore[assignment]
    store.save(ctx)

    response = client.post(
        f"/chat/{ctx.session_id}",
        json={"user_input": "继续推进"},
        headers=_headers("editor"),
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["state"] == SessionState.RECOVERY_REQUIRED.value
    assert "legacy_state" in body["last_error"]
    assert "recovery_endpoint" in body


# ── 5. recovery endpoint semantics ──────────────────────────────────
def test_recover_endpoint_restores_resumable_state_with_audit(api_client):
    client, store, cache = api_client
    ctx = _seed_blocked_session(store, cache, SessionState.RECOVERY_REQUIRED)

    response = client.post(
        f"/sessions/{ctx.session_id}/workflow/recover",
        json={"target_state": "s1_running", "note": "operator confirmed data repair"},
        headers=_headers("admin"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["before"] == SessionState.RECOVERY_REQUIRED.value
    assert body["after"] == SessionState.S1_RUNNING.value
    assert body["last_error"] == ""

    reloaded = store.load(ctx.session_id, "test-tenant")
    assert reloaded is not None
    assert reloaded.current_state == SessionState.S1_RUNNING
    assert reloaded.last_error == ""
    assert "workflow_recovered" in [event.event_type for event in reloaded.audit_events]

    with store._get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM session_events "
            "WHERE session_id=? AND event_type='workflow_recovered'",
            (ctx.session_id,),
        ).fetchone()
    assert row["n"] == 1


def test_recover_endpoint_rejects_non_blocked_session(api_client):
    client, store, cache = api_client
    ctx = ProjectContext(tenant_id="test-tenant", session_name="wf-state")
    ctx.current_state = SessionState.S1_RUNNING
    store.save(ctx)
    cache.set(ctx)

    response = client.post(
        f"/sessions/{ctx.session_id}/workflow/recover",
        json={"target_state": "init"},
        headers=_headers("admin"),
    )

    assert response.status_code == 409, response.text


@pytest.mark.parametrize("target_state", ["complete", "error", "not_a_state"])
def test_recover_endpoint_rejects_invalid_target_state(api_client, target_state):
    client, store, cache = api_client
    ctx = _seed_blocked_session(store, cache, SessionState.ERROR)

    response = client.post(
        f"/sessions/{ctx.session_id}/workflow/recover",
        json={"target_state": target_state},
        headers=_headers("admin"),
    )

    assert response.status_code == 400, response.text


def test_recover_endpoint_returns_404_for_missing_session(api_client):
    client, _, _ = api_client
    response = client.post(
        "/sessions/does-not-exist/workflow/recover",
        json={"target_state": "init"},
        headers=_headers("admin"),
    )
    assert response.status_code == 404


def test_recover_endpoint_requires_editor_role(api_client):
    client, store, cache = api_client
    ctx = _seed_blocked_session(store, cache, SessionState.ERROR)

    response = client.post(
        f"/sessions/{ctx.session_id}/workflow/recover",
        json={"target_state": "init"},
        headers=_headers("viewer"),
    )
    assert response.status_code == 403


def test_recover_endpoint_requires_authentication(api_client):
    client, store, cache = api_client
    ctx = _seed_blocked_session(store, cache, SessionState.ERROR)

    response = client.post(
        f"/sessions/{ctx.session_id}/workflow/recover",
        json={"target_state": "init"},
    )
    assert response.status_code == 401


# ── 6. recover_workflow service contract ────────────────────────────
def test_recover_workflow_rejects_blocked_state_target():
    ctx = _blocked_ctx(SessionState.ERROR)
    with pytest.raises(ValueError):
        recover_workflow(ctx, "error")


def test_recover_workflow_rejects_non_blocked_source():
    ctx = ProjectContext()
    ctx.current_state = SessionState.S1_RUNNING
    with pytest.raises(ValueError):
        recover_workflow(ctx, "init")
