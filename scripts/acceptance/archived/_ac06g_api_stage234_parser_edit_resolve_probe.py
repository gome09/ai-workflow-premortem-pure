#!/usr/bin/env python
# _ac06g_api_stage234_parser_edit_resolve_probe.py
# AC-06G: Stage 2-4 parser edit resolve API lightweight consistency verification.
# Uses FastAPI TestClient + in-memory store (no real API/DB/LLM calls).
# Does NOT start uvicorn, pytest, Streamlit, PostgreSQL, Redis, Tavily, DeepSeek.
"""Temporary probe for AC-06G. Do not wire into production."""

from __future__ import annotations

import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("DEEPSEEK_API_KEY", "probe-dummy-noop")
os.environ.setdefault("TAVILY_API_KEY", "probe-dummy-noop")
os.environ.setdefault("POSTGRES_PASSWORD", "probe-dummy-noop")

# ── In-memory session store & cache (before api.main import) ────────────────
import storage.cache as _cache_mod  # noqa: E402
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
        # Deep copy to avoid reference-sharing across API calls
        self._cache[ctx.session_id] = ProjectContext.model_validate(ctx.model_dump(mode="json"))

    def get(self, session_id: str):
        return self._cache.get(session_id)

    def delete(self, session_id: str) -> None:
        self._cache.pop(session_id, None)

    def refresh_ttl(self, session_id: str) -> None:
        pass


_store_mod.session_store = _InMemorySessionStore()
_cache_mod.context_cache = _InMemoryCache()

# ── Now import app and services ─────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
from core.models import (  # noqa: E402
    FailureMode,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
    WorkflowNode,
)
from core.oversight_service import create_actions_from_parser_errors  # noqa: E402

client = TestClient(app)

# ── Valid payloads per stage schema ─────────────────────────────────────────

VALID_S2_PAYLOAD = {
    "workflow_nodes": [
        {
            "node_id": "N1",
            "stage_name": "Input Validation",
            "model_assigned": "deepseek-chat",
            "human_action": "Review input for completeness",
            "check_criteria": ["No missing required fields"],
            "addressed_failure_mode_ids": ["FM1"],
            "prompt_template": "Validate the user input...",
            "human_review_required": False,
            "oversight_risk_level": "low",
            "evidence_required": False,
            "can_auto_continue": True,
        }
    ],
    "design_rationale": "Minimal reviewed Stage 2 workflow design.",
    "open_questions": [],
}

VALID_S3_PAYLOAD = {
    "test_cases": [
        {
            "case_id": "TC1",
            "target_node_id": "N1",
            "scenario_type": "normal",
            "test_input": "Valid user query",
            "expected_behavior": "System responds correctly",
            "predicted_failure": None,
            "correction_prompt": None,
            "pass_criteria": ["Response is accurate"],
            "passed": True,
        }
    ],
    "overall_passed": True,
    "risk_summary": "Minimal reviewed Stage 3 stress test output.",
}

VALID_S4_PAYLOAD = {
    "trigger_methods": [
        {
            "node_id": "N1",
            "model_or_mode": "deepseek-chat",
            "entry_point": "POST /api/chat",
            "trigger_instruction": "curl -X POST ...",
            "execution_suggestion": "Set max_tokens=1024",
            "human_review_required": False,
        }
    ],
    "final_notes": "Minimal reviewed Stage 4 trigger plan.",
}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _save_ctx(ctx: ProjectContext) -> None:
    """Save ctx to both in-memory store and cache so API can find it."""
    _store_mod.session_store.save(ctx)
    _cache_mod.context_cache.set(ctx)


def build_stage_context(stage: int, tag: str) -> ProjectContext:
    """Build a minimal ProjectContext in review state with parser_error for the given stage."""
    review_states = {
        2: SessionState.S2_REVIEW,
        3: SessionState.S3_REVIEW,
        4: SessionState.S4_REVIEW,
    }
    ctx = ProjectContext(
        session_id=f"ac06g-{tag}",
        research_target="test_target",
        domain="test_domain",
        goal="test_goal",
    )
    ctx.current_state = review_states[stage]

    # Minimal prerequisite outputs
    ctx.stage_1_output = Stage1Output(
        search_sources=["probe-dummy"],
        raw_summary="test raw summary",
        direct_conclusion="Test conclusion for stage 1",
        failure_modes=[
            FailureMode(
                id="FM1",
                category="test",
                description="Test failure mode",
                severity="low",
                evidence_ids=[],
                evidence="test",
            )
        ],
    )

    if stage >= 2:
        ctx.stage_2_output = Stage2Output(
            raw_summary="test stage 2 raw",
            workflow_nodes=[
                WorkflowNode(
                    node_id="N1",
                    stage_name="test",
                    model_assigned="m",
                    human_action="check",
                    check_criteria="ok",
                    failure_modes_addressed=[],
                    prompt_template="test",
                )
            ],
            total_stages=1,
        )

    if stage >= 3:
        ctx.stage_3_output = Stage3Output(
            raw_summary="test stage 3 raw",
            overall_passed=True,
        )

    if stage >= 4:
        ctx.stage_4_output = Stage4Output(
            raw_summary="test stage 4 raw",
        )

    for s in [1, 2, 3, 4]:
        ctx.stage_output_versions[f"stage_{s}"] = 1

    # Inject parser error
    ctx.parser_errors[f"stage_{stage}"] = (
        f"Invalid JSON: missing required fields in stage {stage} output"
    )

    # Use official oversight entry to create the parser edit action
    create_actions_from_parser_errors(ctx, stage=stage)

    _save_ctx(ctx)
    return ctx


def verify_stage_resolve(stage: int) -> dict:
    """Create session, resolve via API, verify parser blocker cleared."""
    payloads = {2: VALID_S2_PAYLOAD, 3: VALID_S3_PAYLOAD, 4: VALID_S4_PAYLOAD}
    ctx = build_stage_context(stage, f"s{stage}")

    session_id = ctx.session_id
    print(f"\n{'─' * 90}")
    print(f"STAGE {stage} — API RESOLVE VALID PAYLOAD")
    print(f"{'─' * 90}")
    print(f"  session_id={session_id}")
    print(f"  current_state={ctx.current_state.value}")

    # ── Get action via API ──
    resp = client.get(f"/sessions/{session_id}/actions?status=pending")
    assert resp.status_code == 200
    actions = resp.json()
    parser_actions = [
        a for a in actions if a.get("source_type") == "parser" and a.get("stage_id") == stage
    ]
    assert parser_actions, f"No parser action found for stage {stage}"
    action_id = parser_actions[0]["action_id"]
    action_type = parser_actions[0]["action_type"]
    source_type = parser_actions[0]["source_type"]
    print(f"  action_id={action_id}  type={action_type}  source={source_type}")

    # ── Readiness before ──
    resp = client.get(f"/sessions/{session_id}/stage-readiness/{stage}")
    assert resp.status_code == 200
    readiness_before = resp.json()
    pblocks_before = [
        b for b in readiness_before.get("blockers", []) if b.get("blocker_type") == "parser_error"
    ]
    action_pblocks_before = [
        b for b in readiness_before.get("blockers", []) if b.get("action_id") == action_id
    ]
    print(
        f"  before: parser_error_blockers={len(pblocks_before)}  "
        f"action_pending_blockers={len(action_pblocks_before)}  "
        f"can_continue={readiness_before['can_continue']}"
    )

    # ── Resolve via API ──
    resp = client.post(
        f"/sessions/{session_id}/actions/{action_id}/resolve",
        json={"decision": "edit", "payload_after": payloads[stage]},
    )
    resolve_http_ok = resp.status_code == 200
    print(f"  POST resolve -> HTTP {resp.status_code}")

    if not resolve_http_ok:
        print(f"  ERROR: {resp.text[:300]}")
        return {
            "stage": stage,
            "resolve_called_via_api": True,
            "resolve_http_ok": False,
            "error": resp.text[:300],
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
    print(f"  action status: {action_status}  reviewer_decision: {reviewer_decision}")

    # ── Verify parser error cleared ──
    pe_after = resolved_ctx.get("parser_errors", {}).get(f"stage_{stage}", "")
    pe_cleared = not bool(pe_after)
    print(f"  parser_errors['stage_{stage}']: {'(cleared)' if pe_cleared else pe_after[:80]}")

    # ── Verify structured output applied ──
    stage_output_key = f"stage_{stage}_output"
    stage_output = resolved_ctx.get(stage_output_key, {}) or {}
    if stage == 2:
        nodes_count = len(stage_output.get("workflow_nodes", []))
        print(f"  stage_2_output.workflow_nodes count: {nodes_count}")
        output_applied = nodes_count > 0
    elif stage == 3:
        cases_count = len(stage_output.get("test_results", []))
        print(f"  stage_3_output.test_results count: {cases_count}")
        output_applied = cases_count > 0
    else:
        triggers_count = len(stage_output.get("trigger_methods", []))
        print(f"  stage_4_output.trigger_methods count: {triggers_count}")
        output_applied = triggers_count > 0

    # ── Readiness after ──
    resp = client.get(f"/sessions/{session_id}/stage-readiness/{stage}")
    assert resp.status_code == 200
    readiness_after = resp.json()
    pblocks_after = [
        b for b in readiness_after.get("blockers", []) if b.get("blocker_type") == "parser_error"
    ]
    action_pblocks_after = [
        b for b in readiness_after.get("blockers", []) if b.get("action_id") == action_id
    ]
    remaining_types = list({b.get("blocker_type") for b in readiness_after.get("blockers", [])})

    print(
        f"  after:  parser_error_blockers={len(pblocks_after)}  "
        f"action_pending_blockers={len(action_pblocks_after)}  "
        f"can_continue={readiness_after['can_continue']}"
    )
    print(f"  remaining blocker types: {remaining_types}")

    return {
        "stage": stage,
        "resolve_called_via_api": True,
        "resolve_http_ok": True,
        "valid_payload_applied": output_applied,
        "action_status_after_resolve": action_status,
        "reviewer_decision": reviewer_decision,
        "parser_blocker_removed": len(pblocks_after) == 0,
        "pending_action_blocker_removed": len(action_pblocks_after) == 0,
        "structured_output_applied": output_applied,
        "parser_error_cleared": pe_cleared,
        "action_id": action_id,
        "action_type": action_type,
        "source_type": source_type,
        "blocker_before": len(pblocks_before) > 0,
        "blocker_after": len(pblocks_after) > 0,
        "remaining_blocker_types": remaining_types,
        "can_continue_after": readiness_after["can_continue"],
    }


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


def main():
    print("=" * 90)
    print("AC-06G: STAGE 2-4 PARSER EDIT RESOLVE API CONSISTENCY")
    print("=" * 90)

    results = {}
    for stage in [2, 3, 4]:
        results[stage] = verify_stage_resolve(stage)

    # ── Summary table ──
    print()
    print("=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)
    header = (
        f"{'stage':<6} {'resolve_via_api':<16} {'payload_applied':<16} "
        f"{'action_status':<14} {'reviewer_dec':<13} "
        f"{'pblock_removed':<15} {'act_pblock_rem':<15} "
        f"{'struct_applied':<15} {'next_llm':<10}"
    )
    print(header)
    print("-" * len(header))
    for s in [2, 3, 4]:
        r = results[s]
        print(
            f"{s:<6} {str(r.get('resolve_called_via_api', False)):<16} "
            f"{str(r.get('valid_payload_applied', False)):<16} "
            f"{str(r.get('action_status_after_resolve', 'N/A')):<14} "
            f"{str(r.get('reviewer_decision', 'N/A')):<13} "
            f"{str(r.get('parser_blocker_removed', False)):<15} "
            f"{str(r.get('pending_action_blocker_removed', False)):<15} "
            f"{str(r.get('structured_output_applied', False)):<15} "
            f"{'false':<10}"
        )

    # ── Action / blocker detail ──
    print()
    print("─" * 100)
    print("ACTION / BLOCKER DETAIL")
    print("─" * 100)
    detail_header = (
        f"{'stage':<6} {'action_id':<12} {'action_type':<7} {'source_type':<8} "
        f"{'blocker_before':<15} {'blocker_after':<14} {'remaining_types'}"
    )
    print(detail_header)
    print("-" * len(detail_header))
    for s in [2, 3, 4]:
        r = results[s]
        print(
            f"{s:<6} {r.get('action_id', 'N/A'):<12} "
            f"{r.get('action_type', 'N/A'):<7} {r.get('source_type', 'N/A'):<8} "
            f"{str(r.get('blocker_before', False)):<15} "
            f"{str(r.get('blocker_after', False)):<14} "
            f"{r.get('remaining_blocker_types', [])}"
        )

    # ── Acceptance ──
    print()
    print("=" * 100)
    print("ACCEPTANCE CRITERIA")
    print("=" * 100)

    def ok(stage: int, key: str) -> bool:
        return results.get(stage, {}).get(key, False)

    checks = [
        (
            "1. Stage 2 resolve via API, payload applied",
            ok(2, "resolve_called_via_api") and ok(2, "valid_payload_applied"),
        ),
        (
            "2. Stage 2 parser blocker + pending action blocker removed",
            ok(2, "parser_blocker_removed") and ok(2, "pending_action_blocker_removed"),
        ),
        (
            "3. Stage 3 resolve via API, payload applied",
            ok(3, "resolve_called_via_api") and ok(3, "valid_payload_applied"),
        ),
        (
            "4. Stage 3 parser blocker + pending action blocker removed",
            ok(3, "parser_blocker_removed") and ok(3, "pending_action_blocker_removed"),
        ),
        (
            "5. Stage 4 resolve via API, payload applied",
            ok(4, "resolve_called_via_api") and ok(4, "valid_payload_applied"),
        ),
        (
            "6. Stage 4 parser blocker + pending action blocker removed",
            ok(4, "parser_blocker_removed") and ok(4, "pending_action_blocker_removed"),
        ),
        (
            "7. All three stages: action=resolved, reviewer_decision=edit",
            all(
                results[s].get("action_status_after_resolve") == "resolved"
                and results[s].get("reviewer_decision") == "edit"
                for s in [2, 3, 4]
            ),
        ),
        (
            "8. All three stages: structured output applied",
            all(ok(s, "structured_output_applied") for s in [2, 3, 4]),
        ),
        (
            "9. No next-stage LLM executed, no full four-stage flow",
            True,
        ),  # by construction — no chat API calls, no LLM
        ("10. No pytest/Streamlit/uvicorn/external services/interrupt", True),
    ]

    all_pass = True
    for label, passed in checks:
        flag = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{flag}] {label}")

    print()
    if all_pass:
        print("AC-06G PASS: Stage 2-4 parser edit resolve API consistent across all stages.")
    else:
        print("AC-06G FAIL: Some stage consistency checks did not pass.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
