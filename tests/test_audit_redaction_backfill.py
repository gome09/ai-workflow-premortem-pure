"""Historical audit/event redaction backfill (T02/T09)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from storage.audit_redaction import BACKFILL_MARKER, redact_legacy_audit_payloads
from storage.backends.sqlite_store import SQLiteSessionStore

TENANT = "tenant-a"
SENSITIVE = "legacy-sensitive-marker"


@pytest.fixture
def store(tmp_path) -> SQLiteSessionStore:
    backend = SQLiteSessionStore(str(tmp_path / "backfill.db"))
    backend.initialize()
    return backend


def _insert_session(store: SQLiteSessionStore, session_id: str, classification: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None).isoformat()
    context = json.dumps({"data_classification": classification})
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO sessions (session_id, tenant_id, current_state, context_json, "
            "projection_state, context_digest, created_at, updated_at, version) "
            "VALUES (?, ?, 'complete', ?, '{}', '', ?, ?, 0)",
            (session_id, TENANT, context, now, now),
        )
        conn.commit()


def _insert_audit(store, session_id: str, event_id: str, payload: dict, metadata: dict) -> None:
    now = datetime.now(UTC).isoformat()
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO audit_events (event_id, session_id, actor, event_type, target_type, "
            "target_id, before_snapshot, after_snapshot, metadata, created_at) "
            "VALUES (?, ?, 'user', 'eval_run_created', 'eval_run', 'run-1', NULL, ?, ?, ?)",
            (
                event_id,
                session_id,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()


def _insert_archive(store, archive_id: str, session_id: str, payload: dict) -> None:
    now = datetime.now(UTC).isoformat()
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO audit_events_archive (archive_id, original_session_id, event_id, actor, "
            "event_type, target_type, target_id, after_snapshot, metadata, original_created_at, "
            "archived_at) VALUES (?, ?, ?, 'user', 'session_purged', 'session', ?, ?, ?, ?, ?)",
            (
                archive_id,
                session_id,
                archive_id,
                session_id,
                json.dumps(payload, ensure_ascii=False),
                json.dumps({"purged_by": "admin"}, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()


def _insert_event(store, session_id: str, payload: dict) -> None:
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO session_events (session_id, event_type, stage, payload, tenant_id) "
            "VALUES (?, 'eval_run_human_calibrated', 3, ?, ?)",
            (session_id, json.dumps(payload, ensure_ascii=False), TENANT),
        )
        conn.commit()


def _read(store, sql: str, params: tuple) -> dict:
    with store._get_conn() as conn:  # noqa: SLF001
        return dict(conn.execute(sql, params).fetchone())


def test_dry_run_reports_but_does_not_write(store) -> None:
    _insert_session(store, "s-1", "business_internal")
    _insert_audit(store, "s-1", "e-1", {"actual_output": SENSITIVE}, {"human_comment": SENSITIVE})

    report = redact_legacy_audit_payloads(store, dry_run=True)

    assert report["tables"]["audit_events"]["changed"] == 1
    row = _read(
        store, "SELECT after_snapshot, metadata FROM audit_events WHERE event_id=?", ("e-1",)
    )
    assert SENSITIVE in row["after_snapshot"]
    assert SENSITIVE in row["metadata"]


def test_apply_redacts_and_is_idempotent(store) -> None:
    _insert_session(store, "s-1", "business_internal")
    _insert_audit(store, "s-1", "e-1", {"actual_output": SENSITIVE}, {"human_comment": SENSITIVE})
    _insert_archive(store, "a-1", "s-1", {"research_target": SENSITIVE})
    _insert_event(store, "s-1", {"human_comment": SENSITIVE, "human_label": "passed"})

    first = redact_legacy_audit_payloads(store, dry_run=False)
    assert first["malformed"] == []

    audit = _read(
        store, "SELECT after_snapshot, metadata FROM audit_events WHERE event_id=?", ("e-1",)
    )
    assert SENSITIVE not in audit["after_snapshot"]
    assert SENSITIVE not in audit["metadata"]
    assert json.loads(audit["metadata"])[BACKFILL_MARKER]["version"]

    archive = _read(
        store,
        "SELECT after_snapshot, metadata FROM audit_events_archive WHERE archive_id=?",
        ("a-1",),
    )
    assert SENSITIVE not in archive["after_snapshot"]
    assert "research_target" not in json.loads(archive["after_snapshot"])

    event = _read(
        store,
        "SELECT payload FROM session_events WHERE session_id=?",
        ("s-1",),
    )
    payload = json.loads(event["payload"])
    assert SENSITIVE not in event["payload"]
    assert payload[BACKFILL_MARKER]["version"]

    second = redact_legacy_audit_payloads(store, dry_run=False)
    assert second["tables"]["audit_events"]["changed"] == 0
    assert second["tables"]["audit_events_archive"]["changed"] == 0
    assert second["tables"]["session_events"]["changed"] == 0


def test_public_demo_parent_stays_readable(store) -> None:
    _insert_session(store, "s-demo", "public_demo")
    _insert_audit(store, "s-demo", "e-demo", {"actual_output": SENSITIVE}, {})

    redact_legacy_audit_payloads(store, dry_run=False)

    row = _read(store, "SELECT after_snapshot FROM audit_events WHERE event_id=?", ("e-demo",))
    assert SENSITIVE in row["after_snapshot"]


def test_orphan_archive_is_conservatively_redacted(store) -> None:
    _insert_archive(store, "a-orphan", "missing-session", {"research_target": SENSITIVE})

    redact_legacy_audit_payloads(store, dry_run=False)

    row = _read(
        store,
        "SELECT after_snapshot FROM audit_events_archive WHERE archive_id=?",
        ("a-orphan",),
    )
    assert SENSITIVE not in row["after_snapshot"]


def test_malformed_json_is_reported_and_untouched(store) -> None:
    _insert_session(store, "s-1", "business_internal")
    now = datetime.now(UTC).isoformat()
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO audit_events (event_id, session_id, actor, event_type, target_type, "
            "target_id, before_snapshot, after_snapshot, metadata, created_at) "
            "VALUES ('e-bad', 's-1', 'user', 'bad', 'session', 's-1', NULL, '{not-json', '{}', ?)",
            (now,),
        )
        conn.commit()

    report = redact_legacy_audit_payloads(store, dry_run=False)

    assert report["malformed"]
    assert report["malformed"][0]["id"] == "e-bad"
    row = _read(store, "SELECT after_snapshot FROM audit_events WHERE event_id=?", ("e-bad",))
    assert row["after_snapshot"] == "{not-json"
