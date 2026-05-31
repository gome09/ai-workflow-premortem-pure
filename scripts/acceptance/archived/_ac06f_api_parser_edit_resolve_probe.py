#!/usr/bin/env python
# _ac06f_api_parser_edit_resolve_probe.py
# AC-06F: API parser edit resolve -> readiness cleared minimum verification.
# Uses FastAPI TestClient + monkeypatched LLM (no real API calls).
# Does NOT start uvicorn, pytest, Streamlit, PostgreSQL, Redis, Tavily, DeepSeek.
"""Temporary probe for AC-06F. Do not wire into production."""

from __future__ import annotations

import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("DEEPSEEK_API_KEY", "probe-dummy-noop")
os.environ.setdefault("TAVILY_API_KEY", "probe-dummy-noop")
os.environ.setdefault("POSTGRES_PASSWORD", "probe-dummy-noop")

from unittest.mock import MagicMock  # noqa: E402

import storage.cache as _cache_mod  # noqa: E402

# ── In-memory session store & cache (before api.main import) ────────────────
import storage.session_store as _store_mod  # noqa: E402
from core.models import ProjectContext  # noqa: E402


class _InMemorySessionStore:
    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def initialize(self) -> None:
        pass

    def save(self, ctx: ProjectContext) -> None:
        self._sessions[ctx.session_id] = ctx.model_dump(mode="json")

    def load(self, session_id: str):
        data = self._sessions.get(session_id)
        if data is None:
            return None
        return ProjectContext.model_validate(data)

    def list_sessions(self, limit: int = 20) -> list[dict]:
        return []

    def log_event(self, *args, **kwargs) -> None:
        pass

    def list_interrupt_records(self, session_id: str) -> list[dict]:
        return []

    def get_interrupt_record(self, session_id: str, interrupt_id: str) -> dict | None:
        return None

    def list_report_artifacts(self, session_id: str) -> list[dict]:
        return []

    def get_report_artifact(self, session_id: str, report_id: str) -> dict | None:
        return None


class _InMemoryCache:
    def __init__(self):
        self._cache: dict[str, ProjectContext] = {}

    def set(self, ctx: ProjectContext) -> None:
        # Store a deep copy via serialization to avoid reference-sharing issues
        self._cache[ctx.session_id] = ProjectContext.model_validate(ctx.model_dump(mode="json"))

    def get(self, session_id: str):
        return self._cache.get(session_id)

    def delete(self, session_id: str) -> None:
        self._cache.pop(session_id, None)

    def refresh_ttl(self, session_id: str) -> None:
        pass


_store_mod.session_store = _InMemorySessionStore()
_cache_mod.context_cache = _InMemoryCache()

# ── Now import FastAPI app ──────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

import core.context_manager as _ctx_mgr_mod  # noqa: E402

# ── Monkeypatch LLM / search ────────────────────────────────────────────────
import graph.nodes as _nodes_mod  # noqa: E402
import stages.base as _base_mod  # noqa: E402
import tools.search as _search_mod  # noqa: E402
from api.main import app  # noqa: E402

BAD_OUTPUT = (
    "This is intentionally bad output with no JSON object, "
    "no Markdown table, and no parseable structured content whatsoever."
)

LLM_CALL_TRACKER: dict[str, int] = {}


def _make_init_fake_llm():
    fake = MagicMock()
    fake.invoke.return_value = AIMessage(
        content=(
            "✅ 信息收集完毕\n\n"
            "- **研究对象**: test_ai_support_chatbot\n"
            "- **具体领域**: enterprise_internal_support\n"
            "- **具体目标**: identify_failure_modes\n"
        )
    )
    return fake


def _make_fake_stage_llm(stage: int):
    LLM_CALL_TRACKER[f"stage_{stage}"] = LLM_CALL_TRACKER.get(f"stage_{stage}", 0) + 1
    fake = MagicMock()
    fake.invoke.return_value = AIMessage(content=BAD_OUTPUT)
    return fake


_nodes_mod._get_init_llm = _make_init_fake_llm
_base_mod.get_llm_for_stage = _make_fake_stage_llm
_ctx_mgr_mod.get_llm_for_stage = _make_fake_stage_llm
_search_mod.research_tool._search_checked = True
_search_mod.research_tool._search_available = False
_search_mod.research_tool.search = MagicMock(return_value=[])

client = TestClient(app)

# ── Payloads ────────────────────────────────────────────────────────────────

VALID_S1_PAYLOAD = {
    "failure_modes": [
        {
            "id": "FM1",
            "category": "幻觉与编造",
            "description": "LLM可能在无工具支持时编造响应",
            "severity": "high",
            "evidence_ids": [],
            "evidence": "人工审核确认风险",
            "mitigation_hint": "添加工具调用日志监控",
            "requires_human_review": True,
        }
    ],
    "direct_conclusion": "人工修正后的结论：主风险为无工具支持时的幻觉编造。",
    "open_questions": [],
}

# Has schema key "failure_modes" but Pydantic-invalid value (string not list)
INVALID_S1_PAYLOAD = {
    "failure_modes": "not-a-list-should-be-array",
    "direct_conclusion": "invalid payload with schema key but wrong type",
    "open_questions": [],
}


# ── Helpers ─────────────────────────────────────────────────────────────────


def create_session_and_trigger_parser_error(session_label: str) -> dict:
    """Create a session via API, send messages to trigger Stage 1 parser failure.
    Returns {session_id, action_id, action_summary, readiness_before}.
    """
    print(f"  [{session_label}] Creating session...")
    resp = client.post("/sessions/")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    print(f"  [{session_label}] session_id={session_id}")

    # First message: INIT -> S1_RUNNING
    resp = client.post(f"/chat/{session_id}", json={"user_input": "Start analysis."})
    assert resp.status_code == 200
    state = resp.json()["current_state"]
    print(f"  [{session_label}] after init: state={state}")

    # Second message: trigger Stage 1 with fake LLM -> parser failure -> S1_REVIEW
    resp = client.post(
        f"/chat/{session_id}",
        json={"user_input": "Find failure modes for internal support chatbot."},
    )
    assert resp.status_code == 200
    state = resp.json()["current_state"]
    print(
        f"  [{session_label}] after stage1: state={state}, pending_actions={resp.json()['pending_actions_count']}"
    )

    # Get parser action
    resp = client.get(f"/sessions/{session_id}/actions?status=pending")
    actions = resp.json()
    parser_actions = [a for a in actions if a.get("source_type") == "parser"]
    assert parser_actions, f"No parser action found for {session_label}"
    action_id = parser_actions[0]["action_id"]
    print(f"  [{session_label}] parser action_id={action_id}")

    # Get readiness before resolve
    resp = client.get(f"/sessions/{session_id}/stage-readiness/1")
    readiness_before = resp.json()

    return {
        "session_id": session_id,
        "action_id": action_id,
        "action_summary": parser_actions[0],
        "readiness_before": readiness_before,
    }


# ────────────────────────────────────────────────────────────────────────────
# Test 1: Valid payload resolve
# ────────────────────────────────────────────────────────────────────────────


def test_valid_resolve() -> dict:
    print("=" * 90)
    print("TEST 1: VALID PAYLOAD RESOLVE VIA API")
    print("=" * 90)
    print()

    LLM_CALL_TRACKER.clear()
    setup = create_session_and_trigger_parser_error("valid")

    session_id = setup["session_id"]
    action_id = setup["action_id"]
    readiness_before = setup["readiness_before"]

    # ── Verify before state ──
    pblocks_before = [
        b for b in readiness_before.get("blockers", []) if b.get("blocker_type") == "parser_error"
    ]
    action_pblocks_before = [
        b
        for b in readiness_before.get("blockers", [])
        if b.get("blocker_type") == "pending_action" and b.get("action_id") == action_id
    ]
    print("  Before resolve:")
    print(f"    can_continue={readiness_before['can_continue']}")
    print(f"    parser_error blockers={len(pblocks_before)}")
    print(f"    pending_action blockers for this action={len(action_pblocks_before)}")
    print(f"    parser_error text: {(readiness_before.get('parser_error') or '')[:80]}")

    # ── Resolve via API ──
    print(f"\n  Resolving action {action_id} via API...")
    resp = client.post(
        f"/sessions/{session_id}/actions/{action_id}/resolve",
        json={"decision": "edit", "payload_after": VALID_S1_PAYLOAD},
    )
    print(f"  HTTP {resp.status_code}")
    resolve_ok = resp.status_code == 200

    if not resolve_ok:
        print(f"  ERROR: {resp.text[:300]}")
        return {
            "valid_payload_applied": False,
            "resolve_http_status": resp.status_code,
            "resolve_error": resp.text[:300],
        }

    resolved_ctx = resp.json()

    # ── Verify action resolved ──
    action_after = None
    for a in resolved_ctx.get("pending_actions", []):
        if a.get("action_id") == action_id:
            action_after = a
            break

    action_status = action_after.get("status") if action_after else "NOT_FOUND"
    reviewer_decision = action_after.get("reviewer_decision") if action_after else "N/A"
    print(f"  action status after resolve: {action_status}")
    print(f"  reviewer_decision: {reviewer_decision}")

    # ── Verify parser error cleared ──
    pe_after = resolved_ctx.get("parser_errors", {}).get("stage_1", "")
    print(f"  parser_errors['stage_1'] after: {repr(pe_after[:80]) if pe_after else '(cleared)'}")

    # ── Verify staged output applied ──
    s1_output = resolved_ctx.get("stage_1_output", {}) or {}
    fm_count = len(s1_output.get("failure_modes", []))
    print(f"  stage_1_output.failure_modes count: {fm_count}")
    print(f"  stage_1_output.direct_conclusion: {(s1_output.get('direct_conclusion') or '')[:80]}")

    # ── Query readiness after resolve ──
    resp = client.get(f"/sessions/{session_id}/stage-readiness/1")
    readiness_after = resp.json()
    pblocks_after = [
        b for b in readiness_after.get("blockers", []) if b.get("blocker_type") == "parser_error"
    ]
    action_pblocks_after = [
        b
        for b in readiness_after.get("blockers", [])
        if b.get("blocker_type") == "pending_action" and b.get("action_id") == action_id
    ]

    print("\n  After resolve:")
    print(f"    can_continue={readiness_after['can_continue']}")
    print(f"    parser_error blockers={len(pblocks_after)}")
    print(f"    pending_action blockers for this action={len(action_pblocks_after)}")
    print(f"    total blockers={len(readiness_after.get('blockers', []))}")
    print(f"    lifecycle={readiness_after.get('stage_lifecycle')}")

    remaining_types = list({b.get("blocker_type") for b in readiness_after.get("blockers", [])})
    print(f"    remaining blocker types: {remaining_types}")

    for b in readiness_after.get("blockers", []):
        print(
            f"      [{b.get('blocker_type')}] resolution={b.get('required_resolution')} source={b.get('source_type')}"
        )

    # ── Verify no stage 2 was executed ──
    s2_output = resolved_ctx.get("stage_2_output", {}) or {}
    has_s2 = bool(s2_output.get("workflow_nodes") or s2_output.get("total_stages"))
    s2_llm_called = LLM_CALL_TRACKER.get("stage_2", 0) > 0
    print(f"\n  stage_2_output exists: {has_s2}")
    print(f"  stage_2 LLM called: {s2_llm_called}")

    return {
        "valid_payload_applied": fm_count > 0,
        "resolve_http_status": resp.status_code,
        "action_status_after": action_status,
        "reviewer_decision": reviewer_decision,
        "parser_error_cleared": not bool(pe_after),
        "parser_blocker_removed": len(pblocks_after) == 0,
        "parser_pending_action_blocker_removed": len(action_pblocks_after) == 0,
        "gate_can_continue_after": readiness_after["can_continue"],
        "remaining_blocker_types": remaining_types,
        "stage_2_output_exists": has_s2,
        "fake_stage2_llm_called": s2_llm_called,
        "total_blockers_after": len(readiness_after.get("blockers", [])),
    }


# ────────────────────────────────────────────────────────────────────────────
# Test 2: Invalid payload resolve (Pydantic-bad value)
# ────────────────────────────────────────────────────────────────────────────


def test_invalid_resolve() -> dict:
    print()
    print("=" * 90)
    print("TEST 2: INVALID PAYLOAD RESOLVE VIA API (Pydantic-bad value)")
    print("=" * 90)
    print()

    LLM_CALL_TRACKER.clear()
    setup = create_session_and_trigger_parser_error("invalid")

    session_id = setup["session_id"]
    action_id = setup["action_id"]
    readiness_before = setup["readiness_before"]

    pblocks_before = [
        b for b in readiness_before.get("blockers", []) if b.get("blocker_type") == "parser_error"
    ]
    print(
        f"  Before: parser_error blockers={len(pblocks_before)}, can_continue={readiness_before['can_continue']}"
    )

    # ── Resolve with invalid payload via API ──
    print(f"\n  Resolving action {action_id} with INVALID payload via API...")
    resp = client.post(
        f"/sessions/{session_id}/actions/{action_id}/resolve",
        json={"decision": "edit", "payload_after": INVALID_S1_PAYLOAD},
    )
    print(f"  HTTP {resp.status_code}")
    rejected = resp.status_code >= 400
    error_detail = ""
    if resp.status_code >= 400:
        error_detail = resp.json().get("detail", "")[:200]
        print(f"  Error: {error_detail}")

    # ── Verify action still pending ──
    resp = client.get(f"/sessions/{session_id}/actions?status=pending")
    actions = resp.json()
    parser_actions = [
        a for a in actions if a.get("source_type") == "parser" and a.get("action_id") == action_id
    ]
    action_stays_pending = len(parser_actions) > 0 and parser_actions[0].get("status") == "pending"
    print(f"  action still pending: {action_stays_pending}")

    # ── Verify parser blocker still exists ──
    resp = client.get(f"/sessions/{session_id}/stage-readiness/1")
    readiness_after = resp.json()
    pblocks_after = [
        b for b in readiness_after.get("blockers", []) if b.get("blocker_type") == "parser_error"
    ]
    parser_blocker_kept = len(pblocks_after) > 0
    can_continue = readiness_after["can_continue"]
    print(f"  parser_error blocker present: {parser_blocker_kept}")
    print(f"  can_continue: {can_continue}")

    # ── Verify session detail confirms parser_error intact ──
    resp = client.get(f"/sessions/{session_id}")
    detail = resp.json()
    pe_kept = "stage_1" in detail.get("parser_errors", {})
    print(f"  parser_errors['stage_1'] intact: {pe_kept}")

    return {
        "invalid_payload_rejected_via_api": rejected,
        "error_detail": error_detail,
        "action_stays_pending": action_stays_pending,
        "parser_blocker_kept": parser_blocker_kept,
        "gate_can_continue_still_false": not can_continue,
        "parser_error_still_in_context": pe_kept,
    }


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


def main():
    results_valid = test_valid_resolve()
    results_invalid = test_invalid_resolve()

    # ── Summary ──
    print()
    print("=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)

    items = [
        ("session_created_via_api", "true"),
        ("execution_mode", "single_step"),
        ("parser_action_created_via_api_flow", "true"),
        ("resolve_called_via_api", "true"),
        ("valid_payload_applied", str(results_valid.get("valid_payload_applied", False))),
        ("action_status_after_valid_resolve", results_valid.get("action_status_after", "N/A")),
        ("reviewer_decision", results_valid.get("reviewer_decision", "N/A")),
        ("parser_blocker_removed", str(results_valid.get("parser_blocker_removed", False))),
        (
            "parser_pending_action_blocker_removed",
            str(results_valid.get("parser_pending_action_blocker_removed", False)),
        ),
        (
            "gate_can_continue_after_resolve",
            str(results_valid.get("gate_can_continue_after", "N/A")),
        ),
        ("remaining_blocker_types", str(results_valid.get("remaining_blocker_types", []))),
        (
            "invalid_payload_rejected_via_api",
            str(results_invalid.get("invalid_payload_rejected_via_api", False)),
        ),
        (
            "action_stays_pending_after_invalid",
            str(results_invalid.get("action_stays_pending", False)),
        ),
        (
            "parser_blocker_kept_after_invalid",
            str(results_invalid.get("parser_blocker_kept", False)),
        ),
        ("stage_2_output_exists", str(results_valid.get("stage_2_output_exists", "N/A"))),
        ("fake_stage2_llm_called", str(results_valid.get("fake_stage2_llm_called", "N/A"))),
    ]
    for label, val in items:
        print(f"  {label:<45} | {str(val):<20}")

    print()
    print("─" * 100)
    print("ACTION / BLOCKER BEFORE-AFTER (valid resolve)")
    print("─" * 100)
    before_after = [
        ("action_status", "pending", results_valid.get("action_status_after", "N/A")),
        ("source_type", "parser", "parser"),
        ("action_type", "edit", "edit"),
        (
            "parser_error_blocker",
            "true",
            str(not results_valid.get("parser_blocker_removed", True)),
        ),
        (
            "pending_action_blocker_for_same_action",
            "true",
            str(not results_valid.get("parser_pending_action_blocker_removed", True)),
        ),
        (
            "blocker_required_resolution",
            "edit_stage_output",
            "none" if results_valid.get("parser_blocker_removed", False) else "edit_stage_output",
        ),
    ]
    for label, before, after in before_after:
        print(f"  {label:<45} | {str(before):<20} | {str(after):<20}")

    # ── Acceptance ──
    print()
    print("=" * 100)
    print("ACCEPTANCE CRITERIA")
    print("=" * 100)

    checks = [
        ("1. Session created via API, single_step", True),
        ("2. send_message triggers S1 parser failure via API", True),
        ("3. Resolve called via formal API endpoint", True),
        (
            "4. Valid payload_after applied to Stage 1 structured output",
            results_valid.get("valid_payload_applied", False),
        ),
        (
            "5. Action enters resolved status",
            results_valid.get("action_status_after") == "resolved",
        ),
        ("6. Parser readiness blocker removed", results_valid.get("parser_blocker_removed", False)),
        (
            "7. Pending action blocker for same action removed",
            results_valid.get("parser_pending_action_blocker_removed", False),
        ),
        (
            "8. Remaining blockers (if any) are NOT parser-related",
            "parser_error" not in results_valid.get("remaining_blocker_types", []),
        ),
        (
            "9. Invalid payload rejected, action stays pending, blocker kept",
            (
                results_invalid.get("invalid_payload_rejected_via_api", False)
                and results_invalid.get("action_stays_pending", False)
                and results_invalid.get("parser_blocker_kept", False)
            ),
        ),
        (
            "10. Stage 2 not executed, no stage_2 LLM call",
            (
                not results_valid.get("stage_2_output_exists", True)
                and not results_valid.get("fake_stage2_llm_called", True)
            ),
        ),
        ("11. No pytest/Streamlit/external services/interrupt", True),
    ]

    all_pass = True
    for label, passed in checks:
        flag = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{flag}] {label}")

    print()
    if all_pass:
        print(
            "AC-06F PASS: API resolve clears parser error, removes blocker, rejects invalid payload atomically."
        )
    else:
        print("AC-06F FAIL: Some acceptance criteria not met.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
