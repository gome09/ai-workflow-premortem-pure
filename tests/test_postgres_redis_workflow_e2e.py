# tests/test_postgres_redis_workflow_e2e.py
"""Milestone 1 P5: PostgreSQL + Redis 下的业务 E2E（CI blocking）。

验收：
- 真实 PostgreSQL 存储 + Redis 热缓存路径完成创建 → 推进 → 暂停（blocking
  action）→ 解决恢复 → 回滚。
- 未知持久化状态在真实存储边界 fail-closed，只能显式 recover 恢复。
- 敏感字段在 PG 中加密落盘，经缓存/存储 round-trip 后明文可读。
- 会话事件 payload 不含用户原文。
- 跨 tenant 读取被拒绝，purge 只删除目标租户会话。

缺少 E2E_DATABASE_URL / E2E_REDIS_URL / DATA_ENCRYPTION_KEY 或非 postgres/mock
配置时：production-safety job（PRODUCTION_SAFETY_REQUIRED=1）必须失败；普通
单元测试 job 允许跳过。
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

_REQUIRED = os.environ.get("PRODUCTION_SAFETY_REQUIRED") == "1"
_DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "")
_REDIS_URL = os.environ.get("E2E_REDIS_URL", "")
_ENCRYPTION_KEY = os.environ.get("DATA_ENCRYPTION_KEY", "")

_missing = [
    name
    for name, value in (
        ("E2E_DATABASE_URL", _DATABASE_URL),
        ("E2E_REDIS_URL", _REDIS_URL),
        ("DATA_ENCRYPTION_KEY", _ENCRYPTION_KEY),
    )
    if not value
]

if _missing:
    message = f"PostgreSQL + Redis workflow E2E requires env: {', '.join(_missing)}"
    if _REQUIRED:
        pytest.fail(message, pytrace=False)
    pytest.skip(message, allow_module_level=True)

import psycopg  # noqa: E402
from alembic.config import Config  # noqa: E402

from alembic import command  # noqa: E402
from core.config import settings  # noqa: E402
from core.models import SessionState  # noqa: E402
from core.risk.assessment import RiskOverridePermissionError  # noqa: E402
from core.session_service import SessionService  # noqa: E402
from core.workflow_state_service import WorkflowBlockedError  # noqa: E402
from scenarios import read_scenario_input  # noqa: E402
from storage.backends.postgres import PostgresSessionStore  # noqa: E402
from storage.cache import ContextCache, context_cache  # noqa: E402
from storage.errors import StaleContextError, TenantIsolationError  # noqa: E402
from storage.session_store import session_store  # noqa: E402

_SCENARIO_ID = "generic_rag_demo"


def _require_runtime() -> None:
    if settings.storage_backend != "postgres":
        pytest.fail("Workflow E2E requires STORAGE_BACKEND=postgres", pytrace=False)
    if settings.llm_mode != "mock":
        pytest.fail("Workflow E2E requires LLM_MODE=mock (no real LLM calls)", pytrace=False)
    if not isinstance(session_store, PostgresSessionStore):
        pytest.fail("Global session_store is not the PostgreSQL backend", pytrace=False)
    if not isinstance(context_cache, ContextCache):
        pytest.fail("Global context_cache is not Redis-backed", pytrace=False)


def _raw_context_json(session_id: str) -> str:
    with psycopg.connect(_DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT context_json::text FROM sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    assert row is not None, f"session {session_id} missing from PostgreSQL"
    return str(row[0])


def _execute(sql: str, params: tuple) -> None:
    with psycopg.connect(_DATABASE_URL, autocommit=True) as conn:
        conn.execute(sql, params)


def _create_tenant(prefix: str) -> str:
    """Create a real tenant row so sessions satisfy the V008 foreign key."""
    return str(session_store.create_tenant(f"{prefix}-{uuid.uuid4().hex}")["tenant_id"])


def _latest_event_payload_text(session_id: str) -> str:
    with psycopg.connect(_DATABASE_URL) as conn:
        row = conn.execute(
            """
            SELECT payload::text FROM session_events
            WHERE session_id = %s AND event_type = 'message'
            ORDER BY created_at DESC LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    assert row is not None, "message event was not persisted"
    return str(row[0])


def _clear_blockers(service: SessionService, session_id: str, tenant_id: str) -> None:
    """Resolve the Python-side blockers that can deterministically appear at S1_REVIEW."""

    ctx = service.get_session(session_id, tenant_id)
    assert ctx is not None
    for evidence in ctx.evidence_sources:
        if not evidence.verified:
            service.verify_evidence(
                session_id, evidence.evidence_id, note="e2e verify", tenant_id=tenant_id
            )
    ctx = service.get_session(session_id, tenant_id)
    assert ctx is not None
    for finding in list(ctx.safety_findings):
        if finding.status == "open" and finding.requires_human_review:
            service.resolve_safety_finding(
                session_id,
                finding.finding_id,
                status="resolved",
                note="e2e resolve",
                tenant_id=tenant_id,
            )
    ctx = service.get_session(session_id, tenant_id)
    assert ctx is not None
    for action in list(ctx.get_pending_actions()):
        if action.action_type == "edit":
            pytest.fail(f"Unexpected edit blocker for mock scenario: {action.action_id}")
        decision = "verify_evidence" if action.action_type == "verify_evidence" else "approve"
        service.resolve_action_with_result(
            session_id=session_id,
            action_id=action.action_id,
            decision=decision,
            note="e2e auto resolve",
            tenant_id=tenant_id,
        )


@pytest.fixture(scope="module", autouse=True)
def migrated_database():
    _require_runtime()
    assert context_cache._client.ping(), "Redis is not reachable"

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    with psycopg.connect(_DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='sessions' "
            "AND column_name IN ('projection_state', 'context_digest')"
        ).fetchall()
    assert {str(row[0]) for row in rows} == {"projection_state", "context_digest"}
    return context_cache


@pytest.fixture
def service(migrated_database):
    created: list[tuple[str, str]] = []
    svc = SessionService()

    def _create(tenant_id: str, scenario_id: str | None = None):
        ctx = svc.create_session(tenant_id=tenant_id, scenario_id=scenario_id)
        created.append((ctx.session_id, tenant_id))
        return ctx

    yield svc, _create

    for session_id, tenant_id in created:
        try:
            if svc.get_session(session_id, tenant_id) is not None:
                svc.delete_session(session_id, purged_by="e2e-cleanup", tenant_id=tenant_id)
        except Exception:
            pass


def test_pg_goal_backfill_encrypts_legacy_plaintext():
    """Historical rows written before the goal-encryption fix can be migrated in place."""
    session_id = str(uuid.uuid4())
    tenant_id = _create_tenant("e2e-goal")
    legacy_goal = "历史明文目标-PG"
    context = {
        "context_schema_version": "0.10.0",
        "session_id": session_id,
        "tenant_id": tenant_id,
        "goal": legacy_goal,
        "data_classification": "business_internal",
        "current_state": "init",
    }
    with psycopg.connect(_DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO sessions "
            "(session_id, current_state, context_json, tenant_id, created_at, updated_at) "
            "VALUES (%s, %s, %s::jsonb, %s::uuid, NOW(), NOW())",
            (session_id, "init", json.dumps(context, ensure_ascii=False), tenant_id),
        )
        conn.commit()

    result = session_store.backfill_goal_encryption(session_ids=[session_id], dry_run=False)
    assert result["changed"] == 1
    assert result["status_counts"] == {"encrypted": 1}

    raw = _raw_context_json(session_id)
    assert "enc:v1:" in raw
    assert legacy_goal not in raw

    loaded = session_store.load(session_id, tenant_id)
    assert loaded is not None
    assert loaded.goal == legacy_goal

    session_store.delete(session_id, tenant_id, system_access=None)


def test_pg_workspace_invitation_and_refresh_role():
    """Real PostgreSQL: same-tenant invite and refresh re-reads current member role."""
    from auth.jwt import verify_token
    from auth.service import auth_service

    suffix = uuid.uuid4().hex
    author = auth_service.register(
        f"pg-author-{suffix}@example.com",
        "author-pass",
        workspace_name="PG Team",
    )
    assert author["role"] == "admin"

    invitation = auth_service.create_invitation(
        author["tenant_id"],
        f"pg-reviewer-{suffix}@example.com",
        "admin",
        author["user_id"],
    )
    reviewer = auth_service.accept_invitation(invitation["token"], "reviewer-pass")
    assert reviewer["tenant_id"] == author["tenant_id"]
    assert reviewer["role"] == "admin"

    auth_service.update_role(reviewer["user_id"], author["tenant_id"], "viewer")
    refreshed = auth_service.refresh(reviewer["refresh_token"])
    assert refreshed["role"] == "viewer"
    assert refreshed["tenant_id"] == author["tenant_id"]
    assert verify_token(refreshed["access_token"]).role == "viewer"


def test_pg_redis_workflow_lifecycle(service, migrated_database):
    svc, create = service
    cache = migrated_database
    tenant_a = _create_tenant("e2e-a")
    tenant_b = _create_tenant("e2e-b")
    scenario_input = read_scenario_input(_SCENARIO_ID)

    # ── 1. create: write-through to PostgreSQL + Redis ────────────────────
    ctx = create(tenant_a, _SCENARIO_ID)
    assert cache._client.exists(f"session:ctx:{tenant_a}:{ctx.session_id}") == 1

    cache.delete(ctx.session_id, tenant_a)
    loaded = svc.get_session(ctx.session_id, tenant_a)
    assert loaded is not None
    assert loaded.current_state == SessionState.INIT
    assert cache.get(ctx.session_id, tenant_a) is not None

    # ── 2. advance: INIT → S1_RUNNING, sensitive fields encrypted at rest ─
    _reply, advanced = svc.send_message(ctx.session_id, scenario_input, tenant_id=tenant_a)
    assert advanced.current_state == SessionState.S1_RUNNING
    assert advanced.research_target, "mock init must extract research_target"
    assert advanced.goal, "mock init must extract goal"

    raw = _raw_context_json(ctx.session_id)
    assert "enc:v1:" in raw, "research_target/conversation must be encrypted in PostgreSQL"
    assert advanced.research_target not in raw, "research_target plaintext leaked into context_json"
    assert advanced.goal not in raw, "goal plaintext leaked into context_json"
    event_payload = _latest_event_payload_text(ctx.session_id)
    assert "研究对象" not in event_payload
    assert "input_sha256" in event_payload

    cache.delete(ctx.session_id, tenant_a)
    reloaded = svc.get_session(ctx.session_id, tenant_a)
    assert reloaded is not None
    assert reloaded.research_target == advanced.research_target
    assert reloaded.goal == advanced.goal
    assert reloaded.current_state == SessionState.S1_RUNNING

    # ── 3. pause: blocking action prevents stage advancement ──────────────
    _reply, reviewing = svc.send_message(ctx.session_id, "开始", tenant_id=tenant_a)
    assert reviewing.current_state == SessionState.S1_REVIEW

    from core.oversight_service import add_action_if_missing

    created_action = add_action_if_missing(
        reviewing,
        stage_id=1,
        action_type="approve",
        title="E2E blocking approval",
        description="Synthetic blocking action to verify pause semantics.",
        risk_level="high",
        source_type="e2e_pause",
        source_id="e2e-pause-1",
        blocking=True,
    )
    assert created_action is not None
    session_store.save(reviewing)
    cache.set(reviewing)

    _reply, paused = svc.send_message(ctx.session_id, "确认", tenant_id=tenant_a)
    assert paused.current_state == SessionState.S1_REVIEW, "blocking action must pause advancement"
    assert any(
        action.action_id == created_action.action_id and action.status == "pending"
        for action in paused.pending_actions
    )

    # ── 4. resume: resolve blockers and approve to S2_RUNNING ─────────────
    svc.resolve_action(
        ctx.session_id,
        created_action.action_id,
        decision="approve",
        note="e2e approve",
        tenant_id=tenant_a,
    )
    _clear_blockers(svc, ctx.session_id, tenant_a)

    _reply, next_stage = svc.send_message(ctx.session_id, "确认", tenant_id=tenant_a)
    assert next_stage.current_state == SessionState.S2_RUNNING

    # ── 5. rollback: stage 2 → stage 1 review ─────────────────────────────
    rollback = svc.request_stage_rollback(
        ctx.session_id,
        from_stage=2,
        to_stage=1,
        reason="e2e rollback",
        tenant_id=tenant_a,
    )
    assert rollback["mutation"]["operation"] == "rollback"
    current = svc.get_session(ctx.session_id, tenant_a)
    assert current is not None
    assert current.current_state == SessionState.S1_REVIEW

    # ── 5b. rerun: re-execute stage 1 after rollback ───────────────────────
    rerun = svc.prepare_stage_rerun(
        ctx.session_id, stage_id=1, reason="e2e rerun", tenant_id=tenant_a
    )
    assert rerun["mutation"]["operation"] == "rerun"
    rerun_ctx = svc.get_session(ctx.session_id, tenant_a)
    assert rerun_ctx is not None
    assert rerun_ctx.current_state == SessionState.S1_RUNNING
    _reply, regenerated = svc.send_message(ctx.session_id, "重新执行", tenant_id=tenant_a)
    assert regenerated.current_state == SessionState.S1_REVIEW
    assert regenerated.stage_1_output is not None

    # ── 5c. optimistic locking: stale save must be rejected ────────────────
    first = session_store.load(ctx.session_id, tenant_a)
    second = session_store.load(ctx.session_id, tenant_a)
    assert first is not None and second is not None
    first.session_name = "e2e optimistic lock"
    session_store.save(first)
    with pytest.raises(StaleContextError):
        session_store.save(second)
    cache.set(first)

    # ── 6. recovery: unknown persisted state fails closed, explicit recover ─
    _execute(
        """
        UPDATE sessions
        SET current_state = 'legacy_state',
            context_json = jsonb_set(context_json, '{current_state}', '"legacy_state"'::jsonb)
        WHERE session_id = %s
        """,
        (ctx.session_id,),
    )
    cache.delete(ctx.session_id, tenant_a)

    sanitized = svc.get_session(ctx.session_id, tenant_a)
    assert sanitized is not None
    assert sanitized.current_state == SessionState.RECOVERY_REQUIRED
    assert "invalid persisted workflow state" in sanitized.last_error

    with pytest.raises(WorkflowBlockedError):
        svc.send_message(ctx.session_id, "继续推进", tenant_id=tenant_a)

    recovered = svc.recover_workflow(
        ctx.session_id, target_state="s1_review", note="e2e recover", tenant_id=tenant_a
    )
    assert recovered["ok"] is True
    assert recovered["before"] == SessionState.RECOVERY_REQUIRED.value
    assert recovered["after"] == SessionState.S1_REVIEW.value

    # ── 6b. risk profile + override audit and tenant isolation ─────────────
    with pytest.raises(RiskOverridePermissionError):
        svc.set_risk_profile(
            ctx.session_id,
            impact=0,
            autonomy=0,
            data_sensitivity=0,
            reversibility=0,
            scale=0,
            external_exposure=0,
            rationale="e2e editor downgrade attempt",
            actor="e2e-editor",
            actor_role="editor",
            tenant_id=tenant_a,
        )
    profile = svc.set_risk_profile(
        ctx.session_id,
        impact=0,
        autonomy=0,
        data_sensitivity=0,
        reversibility=0,
        scale=0,
        external_exposure=0,
        rationale="e2e explicit factors",
        actor="e2e-admin",
        actor_role="admin",
        tenant_id=tenant_a,
    )
    assert profile["effective_tier"] == "low"
    override = svc.override_risk_tier(
        ctx.session_id,
        requested_tier="high",
        reason="e2e override",
        actor="e2e-admin",
        actor_role="admin",
        tenant_id=tenant_a,
    )
    assert override["effective_tier"] == "high"
    stored_override = svc.get_session(ctx.session_id, tenant_a)
    assert stored_override is not None
    override_events = [
        event
        for event in stored_override.audit_events
        if event.event_type == "risk_tier_overridden"
    ]
    assert override_events
    assert override_events[-1].metadata["requested_tier"] == "high"
    assert override_events[-1].metadata["original_tier"] == "low"
    assert override_events[-1].metadata["tenant_id"] == tenant_a
    with pytest.raises(ValueError, match="Session not found"):
        svc.override_risk_tier(
            ctx.session_id,
            requested_tier="low",
            reason="cross tenant attempt",
            actor="other-admin",
            actor_role="admin",
            tenant_id=tenant_b,
        )

    # ── 7. tenant isolation + purge ───────────────────────────────────────
    other = create(tenant_b)
    assert svc.get_session(other.session_id, tenant_a) is None
    assert svc.get_session(ctx.session_id, tenant_b) is None
    with pytest.raises(TenantIsolationError):
        session_store.load(other.session_id, "")
    assert other.session_id not in {
        item["session_id"] for item in svc.list_sessions(tenant_id=tenant_a)
    }

    purged = svc.delete_session(other.session_id, purged_by="e2e-admin", tenant_id=tenant_b)
    assert purged["session_id"] == other.session_id
    assert svc.get_session(other.session_id, tenant_b) is None
    assert cache._client.exists(f"session:ctx:{tenant_b}:{other.session_id}") == 0
    assert svc.get_session(ctx.session_id, tenant_a) is not None
