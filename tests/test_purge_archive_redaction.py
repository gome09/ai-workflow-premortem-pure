"""T02: purge archives only the whitelisted summary fields."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from core.audit_service import append_audit_event
from core.models import ProjectContext, SessionState
from storage.backends.sqlite_store import SQLiteSessionStore

TENANT = "tenant-a"
SENSITIVE = "绝密研究目标-不应进入归档"
SESSION_NAME = "用户输入的敏感会话名"


@pytest.fixture
def store(tmp_path) -> SQLiteSessionStore:
    backend = SQLiteSessionStore(str(tmp_path / "archive.db"))
    backend.initialize()
    return backend


def _summary(session_id: str = "s-1") -> dict:
    return {
        "session_id": session_id,
        "tenant_id": TENANT,
        "session_name": SESSION_NAME,
        "research_target": SENSITIVE,
        "current_state": "complete",
        "data_classification": "business_internal",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-02T00:00:00",
        "purged_by": "admin-user",
        "nested": {"goal": SENSITIVE},
    }


def _archived_purge_event(store: SQLiteSessionStore, session_id: str) -> dict:
    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT after_snapshot, metadata FROM audit_events_archive "
            "WHERE original_session_id=? AND event_type='session_purged'",
            (session_id,),
        ).fetchone()
    assert row is not None
    return {
        "after_snapshot": json.loads(row["after_snapshot"]),
        "metadata": json.loads(row["metadata"]),
    }


@pytest.mark.parametrize(
    "classification", ["business_internal", "sensitive_personal", "public_demo"]
)
def test_purge_summary_is_whitelisted(store, classification) -> None:
    ctx = ProjectContext(
        tenant_id=TENANT,
        session_name=SESSION_NAME,
        research_target=SENSITIVE,
        data_classification=classification,
    )
    ctx.current_state = SessionState.COMPLETE
    append_audit_event(
        ctx,
        actor="user",
        event_type="note",
        target_type="session",
        target_id=ctx.session_id,
        after={"note": SENSITIVE},
    )
    store.create(ctx)

    outcome = store.purge_session(ctx.session_id, TENANT, "admin-user", _summary(ctx.session_id))
    assert outcome.deleted is True

    archived = _archived_purge_event(store, ctx.session_id)
    payload = archived["after_snapshot"]
    dumped = json.dumps(payload, ensure_ascii=False)
    assert SENSITIVE not in dumped
    assert SESSION_NAME not in dumped
    assert "nested" not in dumped
    assert payload["session_id"] == ctx.session_id
    assert payload["tenant_id"] == TENANT
    assert payload["purged_by"] == "admin-user"
    assert payload["archived_audit_events"] >= 1
    assert archived["metadata"] == {"purged_by": "admin-user"}


def test_archive_audit_events_also_sanitizes_caller_summary(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    store.create(ctx)

    count = store.archive_audit_events(ctx.session_id, "admin-user", _summary())
    assert count >= 1

    archived = _archived_purge_event(store, ctx.session_id)
    dumped = json.dumps(archived["after_snapshot"], ensure_ascii=False)
    assert SENSITIVE not in dumped
    assert SESSION_NAME not in dumped
    assert archived["after_snapshot"]["session_id"] == "s-1"


def test_archive_preserves_original_event_hash_and_time(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    event = append_audit_event(
        ctx,
        actor="user",
        event_type="note",
        target_type="session",
        target_id=ctx.session_id,
        before={"note": "before"},
        after={"note": "after"},
    )
    store.create(ctx)
    store.purge_session(ctx.session_id, TENANT, "admin-user", {})

    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT event_id, before_hash, after_hash, original_created_at "
            "FROM audit_events_archive WHERE archive_id=?",
            (f"arch-{event.event_id}",),
        ).fetchone()
    assert row is not None
    assert row["event_id"] == event.event_id
    assert row["before_hash"] == event.before_hash
    assert row["after_hash"] == event.after_hash
    assert row["original_created_at"].startswith(event.created_at.isoformat()[:19])


def test_purge_outcome_distinguishes_stale_and_missing(store) -> None:
    ctx = ProjectContext(tenant_id=TENANT)
    store.create(ctx)
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id=?",
            (datetime.now(UTC).replace(tzinfo=None).isoformat(), ctx.session_id),
        )
        conn.commit()

    stale = store.purge_session(
        ctx.session_id,
        TENANT,
        "retention",
        {},
        retention_cutoff=datetime(2000, 1, 1, tzinfo=UTC),
    )
    assert stale.deleted is False
    assert stale.reason == "stale"
    assert store.load(ctx.session_id, TENANT) is not None

    missing = store.purge_session("missing", TENANT, "retention", {})
    assert missing.deleted is False
    assert missing.reason == "not_found"
