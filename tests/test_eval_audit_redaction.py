"""T09: eval free text is redacted in audit snapshots and session events."""

from __future__ import annotations

import json

import pytest

from core.audit_service import append_audit_event
from core.data_protection import redact_payload
from core.models import ProjectContext
from core.services.access import SessionAccess
from storage.backends.sqlite_store import SQLiteSessionStore

TENANT = "tenant-a"
SENSITIVE = "eval-sensitive-marker-不落库"


@pytest.mark.parametrize(
    "key",
    [
        "input_payload",
        "expected_behavior",
        "actual_output",
        "human_comment",
        "judge_reason",
        "pass_criteria",
        "research_target",
        "goal",
        "session_name",
        "disagreement_reason",
        "rationale",
        "error_message",
        "llm_judge_suggestion",
    ],
)
@pytest.mark.parametrize("value", [SENSITIVE, SENSITIVE * 40, {"nested": SENSITIVE}, [SENSITIVE]])
def test_every_eval_key_is_redacted(key, value) -> None:
    redacted = redact_payload({key: value}, "business_internal")
    assert SENSITIVE not in json.dumps(redacted, ensure_ascii=False)
    assert redacted[key]["_redacted"] is True


def test_redaction_is_idempotent() -> None:
    once = redact_payload({"actual_output": SENSITIVE}, "business_internal")
    twice = redact_payload(once, "business_internal")
    assert once == twice


def test_public_demo_keeps_eval_text_readable() -> None:
    payload = {"actual_output": SENSITIVE}
    assert redact_payload(payload, "public_demo") == payload


def test_audit_snapshot_redacts_eval_run_fields() -> None:
    ctx = ProjectContext(tenant_id=TENANT, session_name="demo")
    event = append_audit_event(
        ctx,
        actor="system",
        event_type="eval_run_created",
        target_type="eval_run",
        target_id="run-1",
        after={
            "input_payload": SENSITIVE,
            "expected_behavior": SENSITIVE,
            "actual_output": SENSITIVE,
            "pass_criteria": [SENSITIVE],
            "run_id": "run-1",
        },
        metadata={"human_comment": SENSITIVE, "judge_reason": SENSITIVE},
    )

    dumped = json.dumps(
        {"snapshot": event.after_snapshot, "metadata": event.metadata},
        ensure_ascii=False,
    )
    assert SENSITIVE not in dumped
    assert event.after_snapshot["run_id"] == "run-1"
    assert event.after_snapshot["actual_output"]["_redacted"] is True
    assert event.metadata["human_comment"]["_redacted"] is True


def test_log_event_redacts_human_calibration_payload(tmp_path) -> None:
    from unittest.mock import patch

    store = SQLiteSessionStore(str(tmp_path / "events.db"))
    store.initialize()
    ctx = ProjectContext(tenant_id=TENANT)
    store.create(ctx)

    with patch("core.session_service.session_store", store):
        SessionAccess()._log_event(
            ctx,
            event_type="eval_run_human_calibrated",
            stage=3,
            payload={
                "human_comment": SENSITIVE,
                "disagreement_reason": SENSITIVE,
                "human_label": "passed",
            },
        )

    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT payload FROM session_events WHERE session_id=? AND "
            "event_type='eval_run_human_calibrated'",
            (ctx.session_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(row["payload"])
    assert SENSITIVE not in json.dumps(payload, ensure_ascii=False)
    assert payload["human_comment"]["_redacted"] is True
    assert payload["disagreement_reason"]["_redacted"] is True
    assert payload["human_label"] == "passed"
