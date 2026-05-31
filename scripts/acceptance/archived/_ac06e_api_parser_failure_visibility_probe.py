#!/usr/bin/env python
# _ac06e_api_parser_failure_visibility_probe.py
# AC-06E: API send_message parser failure -> edit action visibility minimum verification.
# Uses FastAPI TestClient + monkeypatched LLM (no real API calls).
# Does NOT start uvicorn, pytest, Streamlit, PostgreSQL, Redis, Tavily, DeepSeek.
"""Temporary probe for AC-06E. Do not wire into production."""

from __future__ import annotations

import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("DEEPSEEK_API_KEY", "probe-dummy-noop")
os.environ.setdefault("TAVILY_API_KEY", "probe-dummy-noop")  # contains "dummy" -> search disabled
os.environ.setdefault("POSTGRES_PASSWORD", "probe-dummy-noop")

from unittest.mock import MagicMock  # noqa: E402

import storage.cache as _cache_mod  # noqa: E402

# ── Monkeypatch session store / cache BEFORE importing api.main ──────────────
import storage.session_store as _store_mod  # noqa: E402
from core.models import ProjectContext  # noqa: E402


class _InMemorySessionStore:
    """In-memory replacement for PostgreSQL SessionStore."""

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

    def log_event(self, session_id: str, event_type: str, stage, payload: dict) -> None:
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
    """In-memory replacement for Redis ContextCache."""

    def __init__(self):
        self._cache: dict[str, ProjectContext] = {}

    def set(self, ctx: ProjectContext) -> None:
        self._cache[ctx.session_id] = ctx

    def get(self, session_id: str):
        return self._cache.get(session_id)

    def delete(self, session_id: str) -> None:
        self._cache.pop(session_id, None)

    def refresh_ttl(self, session_id: str) -> None:
        pass


_store_mod.session_store = _InMemorySessionStore()
_cache_mod.context_cache = _InMemoryCache()

# ── Now safe to import the FastAPI app ──────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

import core.context_manager as _ctx_mgr_mod  # noqa: E402

# ── Monkeypatch LLM / search dependencies ───────────────────────────────────
import graph.nodes as _nodes_mod  # noqa: E402
import stages.base as _base_mod  # noqa: E402
import tools.search as _search_mod  # noqa: E402
from api.main import app  # noqa: E402

BAD_OUTPUT = (
    "This is intentionally bad output with no JSON object, "
    "no Markdown table, and no parseable structured content whatsoever."
)

# Track LLM calls
LLM_CALL_TRACKER: dict[str, int] = {}


def _make_init_fake_llm():
    """Fake INIT LLM that outputs the confirmation format to trigger INIT -> S1_RUNNING."""
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
    """Fake stage LLM that returns BAD_OUTPUT (no JSON, no Markdown table)."""
    LLM_CALL_TRACKER[f"stage_{stage}"] = LLM_CALL_TRACKER.get(f"stage_{stage}", 0) + 1
    fake = MagicMock()
    fake.invoke.return_value = AIMessage(content=BAD_OUTPUT)
    return fake


_nodes_mod._get_init_llm = _make_init_fake_llm
_base_mod.get_llm_for_stage = _make_fake_stage_llm
_ctx_mgr_mod.get_llm_for_stage = _make_fake_stage_llm

# Disable Tavily search (belt-and-suspenders: env key already contains "dummy")
_search_mod.research_tool._search_checked = True
_search_mod.research_tool._search_available = False
_search_mod.research_tool.search = MagicMock(return_value=[])

# ── TestClient ──────────────────────────────────────────────────────────────
client = TestClient(app)


# ────────────────────────────────────────────────────────────────────────────
# Probe logic
# ────────────────────────────────────────────────────────────────────────────


def run_probe() -> dict:
    results: dict = {}

    # ── Step 1: Create session via API ──────────────────────────────────
    print("=" * 90)
    print("AC-06E: API SEND_MESSAGE PARSER FAILURE -> EDIT ACTION VISIBILITY")
    print("=" * 90)
    print()

    resp = client.post("/sessions/")
    assert resp.status_code == 200, f"Create session failed: {resp.status_code} {resp.text}"
    body = resp.json()
    session_id = body["session_id"]
    init_state = body["current_state"]
    print(f"[1] POST /sessions/ -> {resp.status_code}")
    print(f"    session_id={session_id}")
    print(f"    initial_state={init_state}")
    results["session_created_via_api"] = resp.status_code == 200
    results["session_id"] = session_id
    results["initial_state"] = init_state

    # ── Step 2: Verify session detail ───────────────────────────────────
    resp = client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    detail = resp.json()
    print(f"[2] GET /sessions/{session_id} -> {resp.status_code}")
    print(f"    current_state={detail.get('current_state')}")
    assert detail["current_state"] == "init", f"Expected init, got {detail['current_state']}"
    results["session_detail_ok"] = True

    # ── Step 3: Health check confirms single_step mode ──────────────────
    resp = client.get("/health")
    health = resp.json()
    print(f"[3] GET /health -> workflow_execution_mode={health.get('workflow_execution_mode')}")
    results["execution_mode"] = health.get("workflow_execution_mode", "unknown")
    assert results["execution_mode"] == "single_step", (
        f"Expected single_step, got {results['execution_mode']}"
    )

    # ── Step 4: Send first message -> triggers node_init -> S1_RUNNING ──
    print()
    print("[4] POST /chat/{session_id} (first message: trigger INIT -> S1_RUNNING)")
    LLM_CALL_TRACKER.clear()

    resp = client.post(
        f"/chat/{session_id}",
        json={"user_input": "Start analysis."},
    )
    assert resp.status_code == 200, f"Chat failed: {resp.status_code} {resp.text}"
    chat1 = resp.json()
    print(f"    HTTP {resp.status_code}")
    print(f"    current_state={chat1.get('current_state')}")
    print(f"    pending_actions_count={chat1.get('pending_actions_count')}")
    print(f"    pending_flags_count={chat1.get('pending_flags_count')}")

    # Should be in S1_RUNNING after INIT completes
    state_after_init = chat1["current_state"]
    print(f"    state after first message: {state_after_init}")
    results["state_after_init"] = state_after_init

    # ── Step 5: Send second message -> triggers node_s1_running ─────────
    print()
    print("[5] POST /chat/{session_id} (second message: trigger S1_RUNNING with fake LLM)")

    resp = client.post(
        f"/chat/{session_id}",
        json={"user_input": "Find failure modes for internal support chatbot."},
    )
    assert resp.status_code == 200, f"Chat failed: {resp.status_code} {resp.text}"
    chat2 = resp.json()
    print(f"    HTTP {resp.status_code}")
    print(f"    current_state={chat2.get('current_state')}")
    print(f"    pending_actions_count={chat2.get('pending_actions_count')}")
    print(f"    ai_reply length={len(chat2.get('ai_reply', ''))}")

    state_after = chat2["current_state"]
    results["send_message_via_api"] = resp.status_code == 200
    results["current_state_after_send"] = state_after
    results["pending_actions_count_from_chat"] = chat2.get("pending_actions_count", 0)
    results["fake_stage1_llm_called"] = LLM_CALL_TRACKER.get("stage_1", 0) > 0
    results["fake_stage2_llm_called"] = LLM_CALL_TRACKER.get("stage_2", 0) > 0
    results["real_llm_called"] = False  # by construction

    print(f"    stage_1 llm called: {results['fake_stage1_llm_called']}")
    print(f"    stage_2 llm called: {results['fake_stage2_llm_called']}")

    # ── Step 6: Query session detail to verify state ─────────────────────
    print()
    print(f"[6] GET /sessions/{session_id} (verify session state)")

    resp = client.get(f"/sessions/{session_id}")
    detail2 = resp.json()
    print(f"    current_state={detail2.get('current_state')}")
    print(f"    parser_errors keys={list(detail2.get('parser_errors', {}).keys())}")
    print(f"    pending_actions count={len(detail2.get('pending_actions', []))}")

    pe_keys = list(detail2.get("parser_errors", {}).keys())
    results["parser_errors_present"] = "stage_1" in pe_keys

    # Check stage_2_output
    s2_out = detail2.get("stage_2_output", {}) or {}
    has_s2 = bool(s2_out.get("workflow_nodes") or s2_out.get("total_stages"))
    results["stage_2_output_exists"] = has_s2

    print(f"    stage_2_output exists: {has_s2}")

    # ── Step 7: Query actions endpoint ───────────────────────────────────
    print()
    print(f"[7] GET /sessions/{session_id}/actions (verify parser edit action)")

    resp = client.get(f"/sessions/{session_id}/actions?status=pending")
    assert resp.status_code == 200
    actions = resp.json()
    print(f"    total pending actions: {len(actions)}")

    parser_actions = [a for a in actions if a.get("source_type") == "parser"]
    results["parser_actions_count"] = len(parser_actions)

    action_summary: dict = {}
    if parser_actions:
        pa = parser_actions[0]
        action_summary = {
            "action_id": pa.get("action_id", ""),
            "stage_id": pa.get("stage_id"),
            "action_type": pa.get("action_type", ""),
            "source_type": pa.get("source_type", ""),
            "blocking": pa.get("blocking"),
            "trigger_reason_present": bool(pa.get("trigger_reason")),
            "trigger_reason": (pa.get("trigger_reason") or "")[:150],
            "status": pa.get("status", ""),
        }
        print(f"    action_id={action_summary['action_id']}")
        print(f"    stage_id={action_summary['stage_id']}")
        print(f"    action_type={action_summary['action_type']}")
        print(f"    source_type={action_summary['source_type']}")
        print(f"    blocking={action_summary['blocking']}")
        print(f"    trigger_reason={action_summary['trigger_reason'][:120]}")
    else:
        print("    NO parser actions found!")
        # Show any actions present
        for a in actions:
            print(
                f"    other action: type={a.get('action_type')} source={a.get('source_type')} stage={a.get('stage_id')}"
            )

    results["parser_action_visible_via_api"] = len(parser_actions) > 0
    results["action_summary"] = action_summary

    # ── Step 8: Query stage readiness endpoint ──────────────────────────
    print()
    print(f"[8] GET /sessions/{session_id}/stage-readiness/1 (verify parser blocker)")

    resp = client.get(f"/sessions/{session_id}/stage-readiness/1")
    assert resp.status_code == 200
    readiness = resp.json()
    print(f"    can_continue={readiness.get('can_continue')}")
    print(f"    lifecycle={readiness.get('stage_lifecycle')}")
    print(f"    parser_error present: {bool(readiness.get('parser_error'))}")
    print(f"    parser_error: {(readiness.get('parser_error') or '')[:120]}")

    blockers = readiness.get("blockers", [])
    print(f"    total blockers: {len(blockers)}")
    for b in blockers:
        print(
            f"    blocker: type={b.get('blocker_type')} severity={b.get('severity')} "
            f"resolution={b.get('required_resolution')} action_id={b.get('action_id', '')[:40]}"
        )

    parser_blockers = [b for b in blockers if b.get("blocker_type") == "parser_error"]
    results["readiness_visible_via_api"] = resp.status_code == 200
    results["gate_can_continue"] = readiness.get("can_continue", True)
    results["parser_blockers_count"] = len(parser_blockers)

    blocker_summary: dict = {}
    if parser_blockers:
        pb = parser_blockers[0]
        blocker_summary = {
            "blocker_type": pb.get("blocker_type", ""),
            "severity": pb.get("severity", ""),
            "required_resolution": pb.get("required_resolution", ""),
            "action_id": pb.get("action_id", ""),
            "message": (pb.get("message", "") or "")[:120],
        }
        print(
            f"    parsed blocker: type={blocker_summary['blocker_type']} "
            f"resolution={blocker_summary['required_resolution']} "
            f"action_id={blocker_summary['action_id'][:40]}"
        )
    else:
        print("    NO parser_error blocker found!")

    results["blocker_summary"] = blocker_summary
    results["readiness_has_parser_blocker"] = len(parser_blockers) > 0

    # ── Step 9: Verify session detail shows review state ────────────────
    print()
    print("[9] Final verification: session in review state, stage 2 not executed")

    results["entered_review_state"] = state_after in ("s1_review", "S1_REVIEW")
    print(f"    entered review state: {results['entered_review_state']} (state={state_after})")

    # Verify no stage 2 output was generated
    results["stage2_not_executed"] = not has_s2
    print(f"    stage_2 not executed: {results['stage2_not_executed']}")

    # Verify stage 2 LLM was NOT called
    results["stage2_llm_not_called"] = LLM_CALL_TRACKER.get("stage_2", 0) == 0
    print(f"    stage_2 llm not called: {results['stage2_llm_not_called']}")

    return results


def print_summary_table(results: dict):
    print()
    print("=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)

    items = [
        ("session_created_via_api", "session_created_via_api"),
        ("execution_mode", "execution_mode"),
        ("send_message_via_api", "send_message_via_api"),
        ("fake_stage1_llm_called", "fake_stage1_llm_called"),
        ("real_llm_called", "real_llm_called"),
        ("current_state_after_send", "current_state_after_send"),
        ("parser_action_visible_via_api", "parser_action_visible_via_api"),
        ("action_type", results.get("action_summary", {}).get("action_type", "N/A")),
        ("source_type", results.get("action_summary", {}).get("source_type", "N/A")),
        ("blocking", results.get("action_summary", {}).get("blocking", "N/A")),
        (
            "trigger_reason_present",
            results.get("action_summary", {}).get("trigger_reason_present", "N/A"),
        ),
        ("readiness_visible_via_api", "readiness_visible_via_api"),
        ("blocker_type", results.get("blocker_summary", {}).get("blocker_type", "N/A")),
        ("gate_can_continue", "gate_can_continue"),
        ("stage_2_output_exists", "stage_2_output_exists"),
        ("fake_stage2_llm_called", "fake_stage2_llm_called"),
    ]

    for label, key in items:
        val = results.get(key) if key in results else key
        print(f"  {label:<35} | {str(val):<20}")

    print()
    print("─" * 100)
    print("ACTION / BLOCKER DETAIL")
    print("─" * 100)
    action_summary = results.get("action_summary", {})
    blocker_summary = results.get("blocker_summary", {})

    detail_items = [
        ("action_id", action_summary.get("action_id", "N/A")),
        ("stage_id", action_summary.get("stage_id", "N/A")),
        ("action_type", action_summary.get("action_type", "N/A")),
        ("source_type", action_summary.get("source_type", "N/A")),
        ("blocking", action_summary.get("blocking", "N/A")),
        ("blocker_type", blocker_summary.get("blocker_type", "N/A")),
        ("blocker_required_resolution", blocker_summary.get("required_resolution", "N/A")),
        ("blocker_action_id", blocker_summary.get("action_id", "N/A")),
    ]
    for label, val in detail_items:
        print(f"  {label:<35} | {str(val):<40}")


def main():
    results = run_probe()
    print_summary_table(results)

    # ── Acceptance verdict ───────────────────────────────────────────────
    action_summary = results.get("action_summary", {})
    blocker_summary = results.get("blocker_summary", {})

    checks = [
        ("1. API create session OK", results.get("session_created_via_api", False)),
        ("2. Execution mode single_step", results.get("execution_mode") == "single_step"),
        (
            "3. send_message triggers S1 parser failure",
            (
                results.get("send_message_via_api", False)
                and results.get("fake_stage1_llm_called", False)
            ),
        ),
        ("4. Enters s1_review state", results.get("entered_review_state", False)),
        (
            "5. Parser edit action visible via API",
            results.get("parser_action_visible_via_api", False),
        ),
        ("6a. action_type=edit", action_summary.get("action_type") == "edit"),
        ("6b. source_type=parser", action_summary.get("source_type") == "parser"),
        ("6c. stage_id=1", action_summary.get("stage_id") == 1),
        ("6d. blocking=true", action_summary.get("blocking") is True),
        ("6e. trigger_reason present", action_summary.get("trigger_reason_present", False)),
        ("7a. Readiness visible", results.get("readiness_visible_via_api", False)),
        ("7b. parser_error blocker exists", results.get("readiness_has_parser_blocker", False)),
        ("7c. can_continue=false", results.get("gate_can_continue") is False),
        (
            "7d. required_resolution=edit_stage_output",
            blocker_summary.get("required_resolution") == "edit_stage_output",
        ),
        ("8. Blocker links to action_id", bool(blocker_summary.get("action_id"))),
        ("9. Stage 2 not executed", results.get("stage2_not_executed", False)),
        ("10. No external services called", True),  # by construction
    ]

    print()
    print("=" * 100)
    print("ACCEPTANCE CRITERIA")
    print("=" * 100)
    all_pass = True
    for label, passed in checks:
        flag = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{flag}] {label}")

    print()
    if all_pass:
        print(
            "AC-06E PASS: API send_message triggers parser failure -> edit action visible via API."
        )
    else:
        print("AC-06E FAIL: Some acceptance criteria not met.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
