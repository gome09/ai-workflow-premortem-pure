# tests/test_evidence_verification_identity.py
"""证据核验人身份：只取 JWT user_id，审计 actor 仍为枚举，历史 user 不伪造。"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core.evidence_service import link_failure_modes_to_evidence
from core.models import (
    EvidenceSource,
    FailureMode,
    ProjectContext,
    SessionState,
    Stage1Output,
)
from core.oversight_service import create_actions_from_evidence_gaps, resolve_action
from core.services.evidence import EvidenceService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "tenant-evidence-identity"


@pytest.fixture
def identity_env(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "evidence-identity.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield store


def _ctx(evidence_ids: tuple[str, ...] = ("EVID-1", "EVID-2")) -> ProjectContext:
    ctx = ProjectContext(
        tenant_id=_TENANT,
        research_target="GPT-4o",
        domain="法律文书生成",
        goal="降低虚构条文引用",
        created_by="creator-user",
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.S1_REVIEW
    for index, evidence_id in enumerate(evidence_ids, 1):
        ctx.evidence_sources.append(
            EvidenceSource(
                evidence_id=evidence_id,
                session_id=ctx.session_id,
                title=f"Official report {index}",
                source_type="official_doc",
                credibility_score=0.9,
            )
        )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="引用未核验来源",
                severity="high",
                evidence_ids=list(evidence_ids),
            )
        ]
    )
    ctx.stage_output_versions["stage_1"] = 1
    link_failure_modes_to_evidence(ctx)
    create_actions_from_evidence_gaps(ctx, stage=1)
    assert ctx.pending_actions, "fixture 必须产生一条 verify_evidence 动作"
    return ctx


def _reload(store: SQLiteSessionStore, session_id: str) -> ProjectContext:
    ctx = store.load(session_id, _TENANT)
    assert ctx is not None
    return ctx


def _verified_events(store: SQLiteSessionStore, session_id: str, evidence_id: str) -> list[dict]:
    """审计事件全文在 audit_events 表；context_json 只保留事件身份字段。"""
    with store._get_conn() as conn:  # noqa: SLF001 - test helper
        rows = conn.execute(
            "SELECT actor, metadata FROM audit_events "
            "WHERE session_id=? AND event_type='evidence_verified' AND target_id=? "
            "ORDER BY created_at",
            (session_id, evidence_id),
        ).fetchall()
    return [{"actor": row["actor"], "metadata": json.loads(row["metadata"])} for row in rows]


def test_single_verify_records_jwt_identity(identity_env):
    ctx = _ctx()
    identity_env.create(ctx)

    EvidenceService().verify_evidence(
        ctx.session_id,
        "EVID-1",
        note="核验 E1",
        tenant_id=_TENANT,
        actor_id="user-a",
        actor_role="editor",
    )

    stored = _reload(identity_env, ctx.session_id)
    evidence = {item.evidence_id: item for item in stored.evidence_sources}
    assert evidence["EVID-1"].verified_by == "user-a"
    events = _verified_events(identity_env, ctx.session_id, "EVID-1")
    assert len(events) == 1
    assert events[0]["actor"] == "user"
    assert events[0]["metadata"]["reviewer_id"] == "user-a"
    assert events[0]["metadata"]["reviewer_role"] == "editor"


def test_two_members_are_distinguishable(identity_env):
    ctx = _ctx()
    identity_env.create(ctx)
    service = EvidenceService()

    service.verify_evidence(
        ctx.session_id,
        "EVID-1",
        note="A",
        tenant_id=_TENANT,
        actor_id="user-a",
        actor_role="editor",
    )
    service.verify_evidence(
        ctx.session_id,
        "EVID-2",
        note="B",
        tenant_id=_TENANT,
        actor_id="user-b",
        actor_role="admin",
    )

    stored = _reload(identity_env, ctx.session_id)
    by_id = {item.evidence_id: item for item in stored.evidence_sources}
    assert by_id["EVID-1"].verified_by == "user-a"
    assert by_id["EVID-2"].verified_by == "user-b"


def test_auto_close_does_not_overwrite_first_reviewer(identity_env):
    ctx = _ctx()
    identity_env.create(ctx)
    service = EvidenceService()

    service.verify_evidence(
        ctx.session_id,
        "EVID-1",
        note="A first",
        tenant_id=_TENANT,
        actor_id="user-a",
        actor_role="editor",
    )
    first = _reload(identity_env, ctx.session_id).evidence_sources[0]
    first_at = first.verified_at

    service.verify_evidence(
        ctx.session_id,
        "EVID-2",
        note="B completes",
        tenant_id=_TENANT,
        actor_id="user-b",
        actor_role="editor",
    )

    stored = _reload(identity_env, ctx.session_id)
    evidence = {item.evidence_id: item for item in stored.evidence_sources}
    assert evidence["EVID-1"].verified_by == "user-a"
    assert evidence["EVID-1"].verified_at == first_at
    assert evidence["EVID-2"].verified_by == "user-b"
    assert stored.pending_actions[0].status == "resolved"


def test_explicit_group_verification_uses_actor_without_overwriting_history(identity_env):
    ctx = _ctx()
    ctx.evidence_sources[0].verified = True
    ctx.evidence_sources[0].verified_by = "user"
    ctx.evidence_sources[0].verification_note = "历史数据"
    identity_env.create(ctx)
    action = ctx.pending_actions[0]

    resolve_action(
        ctx,
        action_id=action.action_id,
        decision="verify_evidence",
        note="整组核验",
        actor_id="user-c",
        actor_role="admin",
    )
    identity_env.save(ctx)

    stored = _reload(identity_env, ctx.session_id)
    evidence = {item.evidence_id: item for item in stored.evidence_sources}
    assert evidence["EVID-1"].verified_by == "user"
    assert evidence["EVID-1"].verification_note == "历史数据"
    assert evidence["EVID-2"].verified_by == "user-c"
    events = _verified_events(identity_env, ctx.session_id, "EVID-2")
    assert events[-1]["actor"] == "user"
    assert events[-1]["metadata"]["reviewer_id"] == "user-c"
    assert events[-1]["metadata"]["reviewer_role"] == "admin"


# ── API：身份只取 JWT，请求体伪造 reviewer_id 无效 ──────────────────────────


@pytest.fixture
def identity_client(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("psycopg")
    pytest.importorskip("redis")
    pytest.importorskip("langchain_core")
    pytest.importorskip("langchain_openai")
    pytest.importorskip("tavily")
    pytest.importorskip("prometheus_fastapi_instrumentator")

    from fastapi.testclient import TestClient

    from tests.auth_seed import seed_sqlite_user

    store = SQLiteSessionStore(str(tmp_path / "evidence-identity-api.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        seed_sqlite_user(store, user_id="user-a", tenant_id=_TENANT, role="editor")
        seed_sqlite_user(store, user_id="user-b", tenant_id=_TENANT, role="editor")
        from api.main import app

        yield TestClient(app), store


def _headers(user_id: str, role: str = "editor") -> dict:
    from auth.jwt import create_access_token

    token = create_access_token({"sub": user_id, "tenant_id": _TENANT, "role": role})
    return {"Authorization": f"Bearer {token}"}


def test_api_uses_jwt_identity_and_ignores_forged_reviewer_id(identity_client):
    client, store = identity_client
    ctx = _ctx(("EVID-1", "EVID-2"))
    # API 流程不依赖预先存在的 pending action，保持上下文简单。
    ctx.pending_actions = []
    store.create(ctx)

    first = client.post(
        f"/sessions/{ctx.session_id}/evidence/EVID-1/verify",
        json={"note": "A 核验"},
        headers=_headers("user-a"),
    )
    assert first.status_code == 200, first.text

    forged = client.post(
        f"/sessions/{ctx.session_id}/evidence/EVID-2/verify",
        json={"note": "B 伪造身份", "reviewer_id": "user-b"},
        headers=_headers("user-a"),
    )
    assert forged.status_code == 200, forged.text

    stored = _reload(store, ctx.session_id)
    by_id = {item.evidence_id: item for item in stored.evidence_sources}
    assert by_id["EVID-1"].verified_by == "user-a"
    assert by_id["EVID-2"].verified_by == "user-a", "请求体 reviewer_id 不得生效"
    for evidence_id in ("EVID-1", "EVID-2"):
        events = _verified_events(store, ctx.session_id, evidence_id)
        assert events[-1]["actor"] == "user"
        assert events[-1]["metadata"]["reviewer_id"] == "user-a"


def test_api_distinguishes_two_jwt_members(identity_client):
    client, store = identity_client
    ctx = _ctx(("EVID-1", "EVID-2"))
    ctx.pending_actions = []
    store.create(ctx)

    assert (
        client.post(
            f"/sessions/{ctx.session_id}/evidence/EVID-1/verify",
            json={"note": "A"},
            headers=_headers("user-a"),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/sessions/{ctx.session_id}/evidence/EVID-2/verify",
            json={"note": "B"},
            headers=_headers("user-b"),
        ).status_code
        == 200
    )

    stored = _reload(store, ctx.session_id)
    by_id = {item.evidence_id: item for item in stored.evidence_sources}
    assert {by_id["EVID-1"].verified_by, by_id["EVID-2"].verified_by} == {"user-a", "user-b"}
