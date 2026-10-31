# tests/test_data_protection_redaction.py
"""Milestone 1 P2: 敏感原文不得无必要进入 event / audit payload。

验收：
- 统一脱敏策略 deterministic：同输入必得同信封；public_demo 保留可读内容。
- audit 快照 / metadata 的自由文本字段被替换为 sha256 摘要信封，原文不落库；
  before_hash / after_hash 仍基于原文计算，便于可复核性。
- session_events 的自由文本字段同样脱敏；send_message 只落输入指纹。
"""

from __future__ import annotations

import hashlib
import json

import pytest

from core.audit_service import append_audit_event, stable_hash
from core.data_protection import MAX_PLAIN_STRING, redact_payload, redacted_envelope
from core.models import PendingHumanAction, ProjectContext
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

SENSITIVE_TEXT = "患者张三 身份证310101199001011234 处方：华法林 3mg"


@pytest.fixture
def store(tmp_path):
    backend = SQLiteSessionStore(db_path=str(tmp_path / "redaction.db"))
    backend.initialize()
    return backend


@pytest.fixture
def isolated_service(store):
    from unittest.mock import patch

    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService(), store, cache


def _event_payload(store, session_id: str, event_type: str) -> dict:
    with store._get_conn() as conn:
        row = conn.execute(
            "SELECT payload FROM session_events WHERE session_id=? AND event_type=? "
            "ORDER BY event_id DESC LIMIT 1",
            (session_id, event_type),
        ).fetchone()
    assert row is not None
    return json.loads(row["payload"])


# ── 1. 脱敏原语 ─────────────────────────────────────────────────────
def test_redact_payload_is_deterministic_and_lossless_about_identity():
    payload = {
        "note": SENSITIVE_TEXT,
        "action_id": "ACT-1",
        "nested": [{"description": SENSITIVE_TEXT}],
    }

    first = redact_payload(payload, "business_internal")
    second = redact_payload(dict(payload), "business_internal")

    assert first == second
    assert first["note"]["_redacted"] is True
    assert first["note"]["sha256"] == redacted_envelope(SENSITIVE_TEXT)["sha256"]
    assert first["note"]["length"] == len(SENSITIVE_TEXT)
    assert SENSITIVE_TEXT not in json.dumps(first, ensure_ascii=False)
    # 非自由文本键保持可读，便于审计定位。
    assert first["action_id"] == "ACT-1"
    assert first["nested"][0]["description"]["_redacted"] is True


def test_redact_payload_keeps_public_demo_readable():
    payload = {"note": SENSITIVE_TEXT}
    assert redact_payload(payload, "public_demo") == payload


def test_redact_payload_truncates_long_plain_strings():
    long_value = "x" * (MAX_PLAIN_STRING + 10)
    redacted = redact_payload({"detail": long_value}, "business_internal")

    assert redacted["detail"].startswith("x" * MAX_PLAIN_STRING)
    assert redacted["detail"].endswith(f"<truncated:{len(long_value)} chars>")
    assert long_value not in redacted["detail"]


# ── 2. audit payload ────────────────────────────────────────────────
def test_audit_snapshot_redacts_free_text_but_keeps_original_hash():
    ctx = ProjectContext(tenant_id="tenant-a")
    action = PendingHumanAction(
        session_id=ctx.session_id,
        stage_id=1,
        action_type="edit",
        title="补充证据",
        description=SENSITIVE_TEXT,
    )

    event = append_audit_event(
        ctx,
        actor="system",
        event_type="human_action_created",
        target_type="human_action",
        target_id=action.action_id,
        after=action,
        metadata={"source_id": "FM-001", "note": SENSITIVE_TEXT},
    )

    assert event.after_hash == stable_hash(action)
    snapshot = event.after_snapshot or {}
    assert snapshot["description"]["_redacted"] is True
    assert snapshot["title"]["_redacted"] is True
    assert SENSITIVE_TEXT not in json.dumps(snapshot, ensure_ascii=False)
    assert event.metadata["note"]["_redacted"] is True
    assert event.metadata["source_id"] == "FM-001"


def test_audit_snapshot_stays_readable_for_public_demo():
    ctx = ProjectContext(tenant_id="tenant-a")
    ctx.data_classification = "public_demo"

    event = append_audit_event(
        ctx,
        actor="user",
        event_type="demo_note",
        target_type="session",
        target_id=ctx.session_id,
        after={"note": "演示备注可读"},
    )

    assert event.after_snapshot == {"note": "演示备注可读"}


# ── 3. session_events payload ───────────────────────────────────────
def test_log_event_redacts_note_for_business_internal(isolated_service):
    service, store, _ = isolated_service
    ctx = service.create_session(tenant_id="tenant-a")
    assert ctx.data_classification == "business_internal"

    service._log_event(
        ctx,
        event_type="human_action_resolved",
        stage=1,
        payload={"action_id": "ACT-1", "decision": "approve", "note": SENSITIVE_TEXT},
    )

    payload = _event_payload(store, ctx.session_id, "human_action_resolved")
    assert payload["action_id"] == "ACT-1"
    assert payload["decision"] == "approve"
    assert payload["note"]["_redacted"] is True
    assert SENSITIVE_TEXT not in json.dumps(payload, ensure_ascii=False)


def test_log_event_keeps_note_for_public_demo(isolated_service):
    service, store, _ = isolated_service
    ctx = ProjectContext(tenant_id="tenant-a", session_name="demo")
    ctx.data_classification = "public_demo"
    store.save(ctx)

    service._log_event(
        ctx,
        event_type="human_action_resolved",
        stage=1,
        payload={"action_id": "ACT-1", "decision": "approve", "note": "演示说明"},
    )

    payload = _event_payload(store, ctx.session_id, "human_action_resolved")
    assert payload["note"] == "演示说明"


def test_send_message_event_stores_only_input_fingerprint(isolated_service):
    from unittest.mock import patch

    service, store, _ = isolated_service
    ctx = service.create_session(tenant_id="tenant-a")

    with patch("core.session_service.execute_one_turn", side_effect=lambda value: value):
        service.send_message(ctx.session_id, SENSITIVE_TEXT, tenant_id="tenant-a")

    payload = _event_payload(store, ctx.session_id, "message")
    assert payload["input_sha256"] == hashlib.sha256(SENSITIVE_TEXT.encode("utf-8")).hexdigest()
    assert payload["input_length"] == len(SENSITIVE_TEXT)
    assert "user_input" not in payload
    assert SENSITIVE_TEXT not in json.dumps(payload, ensure_ascii=False)
