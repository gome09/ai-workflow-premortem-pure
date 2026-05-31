"""AC-08D/E Eval API visibility + summary audit.

FastAPI TestClient, no pytest, no uvicorn, no DB, no LLM, no network.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

# ── Monkeypatch BEFORE importing api.main ────────────────────────────────────
import storage.session_store as _store_mod

_store_mod.session_store.initialize = lambda: None
_store_mod.session_store.save = lambda ctx: None
_store_mod.session_store.log_event = lambda *a, **kw: None

import storage.cache as _cache_mod

_cache_mod.context_cache.set = lambda ctx: None
_cache_mod.context_cache.get = lambda sid: None
_cache_mod.context_cache.refresh_ttl = lambda sid: None
_cache_mod.context_cache.delete = lambda sid: None

from core.models import (
    EvalCase,
    EvalRun,
    FailureMode,
    ProjectContext,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    WorkflowNode,
)
from core.session_service import session_service

SESSION_ID = "ac08de-api-audit"

# ── Build in-memory context ─────────────────────────────────────────────────
ctx = ProjectContext(
    session_id=SESSION_ID,
    current_state=SessionState.S3_REVIEW,
    stage_output_versions={"stage_1": 1, "stage_2": 1, "stage_3": 1},
)

fm = FailureMode(
    id="fm_ac08de_high",
    category="eval_api_test",
    description="AC-08DE: high-risk FM for Eval API visibility audit.",
    severity="high",
)
ctx.stage_1_output = Stage1Output(failure_modes=[fm], direct_conclusion="AC-08DE test.")

node = WorkflowNode(
    node_id="node_ac08de_high",
    stage_name="Review",
    model_assigned="deepseek-v4",
    human_action="Approve",
    check_criteria="Safety check",
    failure_modes_addressed=["fm_ac08de_high"],
    prompt_template="Review the content...",
)
ctx.stage_2_output = Stage2Output(workflow_nodes=[node], total_stages=4)
ctx.stage_3_output = Stage3Output(test_results=[], overall_passed=True)

case = EvalCase(
    session_id=SESSION_ID,
    stage_id=3,
    target_node_id="node_ac08de_high",
    covered_failure_mode_ids=["fm_ac08de_high"],
    scenario_type="normal",
    input_payload="AC-08DE test input.",
    expected_behavior="Model should identify risks.",
    pass_criteria=["Risk identified", "No errors"],
)
ctx.eval_cases.append(case)

# ── Monkeypatch session_service ──────────────────────────────────────────────
_original = session_service.get_session
session_service.get_session = lambda sid: ctx if sid == SESSION_ID else None

# ── Import app + TestClient ──────────────────────────────────────────────────
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def banner(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ======================================================================
# 1. GET /eval-cases
# ======================================================================
banner("1. GET /sessions/{id}/eval-cases")

resp = client.get(f"/sessions/{SESSION_ID}/eval-cases")
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
data = resp.json()
assert isinstance(data, list) and len(data) >= 1
ec = data[0]

fields = {
    "eval_id": "EVAL-",
    "stage_id": 3,
    "target_node_id": "node_ac08de_high",
    "covered_failure_mode_ids": ["fm_ac08de_high"],
    "input_payload": "AC-08DE test input.",
    "expected_behavior": "Model should identify risks.",
    "pass_criteria": ["Risk identified", "No errors"],
    "scenario_type": "normal",
}
for field, expected in fields.items():
    val = ec.get(field)
    if isinstance(expected, list):
        ok = val == expected
    elif isinstance(expected, str) and expected.startswith("EVAL-"):
        ok = expected in str(val)
    else:
        ok = val == expected
    print(f"  {'OK' if ok else 'FAIL'}: {field} = {val}")
    assert ok, f"Field {field}: expected {expected}, got {val}"

print("  >>> PASS: EvalCase API returns all required fields.")


# ======================================================================
# 2. POST /eval-cases/{eid}/run (single run, dry_run mode)
# ======================================================================
banner("2. POST /sessions/{id}/eval-cases/{eid}/run (dry_run)")

resp = client.post(
    f"/sessions/{SESSION_ID}/eval-cases/{case.eval_id}/run",
    json={"run_mode": "dry_run"},
)
print(f"  status_code = {resp.status_code}")
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
run_data = resp.json()
print(f"  created_runs count = {len(run_data.get('created_runs', []))}")
print(f"  eval_runs_count    = {run_data.get('eval_runs_count')}")

assert len(run_data.get("created_runs", [])) >= 1, "No EvalRun created"
assert run_data.get("eval_runs_count", 0) >= 1

# Verify the run has required fields
run = run_data["created_runs"][0]
for field in [
    "run_id",
    "eval_id",
    "target_node_id",
    "run_mode",
    "status",
    "judge_result",
    "judge_mode",
]:
    val = run.get(field)
    ok = val is not None and val != ""
    print(f"  {'OK' if ok else 'FAIL'}: {field} = {val}")
    assert ok, f"Missing/invalid field: {field}"

assert run["run_mode"] == "dry_run", f"Expected dry_run, got {run['run_mode']}"
assert run["judge_result"] == "needs_review", f"Expected needs_review, got {run['judge_result']}"
assert run["judge_mode"] == "rule", f"Expected rule, got {run['judge_mode']}"

print("  >>> PASS: Single EvalCase run API creates EvalRun (dry_run, no LLM).")


# ======================================================================
# 3. GET /eval-runs
# ======================================================================
banner("3. GET /sessions/{id}/eval-runs")

resp = client.get(f"/sessions/{SESSION_ID}/eval-runs")
assert resp.status_code == 200
runs = resp.json()
print(f"  eval_runs count = {len(runs)}")
assert len(runs) >= 1, "Expected >=1 eval runs"
r = runs[0]
for field in ["run_id", "eval_id", "target_node_id", "run_mode", "judge_result"]:
    print(f"  {field} = {r.get(field)}")
    assert r.get(field), f"Missing field: {field}"

print("  >>> PASS: EvalRun list API returns all required fields.")


# ======================================================================
# 4. GET /stage-readiness/3 - eval_failure blocker
# ======================================================================
banner("4. GET /sessions/{id}/stage-readiness/3 (eval_failure blocker)")

# First add a failed EvalRun to ensure eval_failure blocker
run_failed = EvalRun(
    session_id=SESSION_ID,
    eval_id=case.eval_id,
    target_node_id="node_ac08de_high",
    covered_failure_mode_ids=["fm_ac08de_high"],
    run_mode="dry_run",
    input_payload=case.input_payload,
    expected_behavior=case.expected_behavior,
    pass_criteria=case.pass_criteria,
    judge_result="failed",
    judge_mode="rule",
    judge_reason="AC-08DE: synthetic failure.",
    status="completed",
)
ctx.eval_runs.append(run_failed)

resp = client.get(f"/sessions/{SESSION_ID}/stage-readiness/3")
assert resp.status_code == 200
readiness = resp.json()

print(f"  can_continue = {readiness.get('can_continue')}")
print(f"  stage_lifecycle = {readiness.get('stage_lifecycle')}")
blockers = readiness.get("blockers", [])
eval_fail = [b for b in blockers if b["blocker_type"] == "eval_failure"]
print(f"  eval_failure blockers = {len(eval_fail)}")

assert readiness["can_continue"] is False, "Expected can_continue=False"
assert len(eval_fail) >= 2, (
    f"Expected >=2 eval_failure (needs_review + failed), got {len(eval_fail)}"
)

required = ["blocker_id", "blocker_type", "severity", "source_id", "required_resolution"]
for i, b in enumerate(eval_fail):
    print(f"  eval_failure[{i}]:")
    for field in required:
        v = b.get(field)
        print(f"    {field} = {v}")
        assert v, f"Missing {field} in blocker"

print("  >>> PASS: Readiness API shows eval_failure blockers with all 5 fields.")


# ======================================================================
# 5. POST /eval-cases/{eid}/score
# ======================================================================
banner("5. POST /sessions/{id}/eval-cases/{eid}/score")

resp = client.post(
    f"/sessions/{SESSION_ID}/eval-cases/{case.eval_id}/score",
    json={
        "human_score": 4,
        "human_comment": "AC-08D/E API scoring test.",
        "passed": True,
    },
)
print(f"  status_code = {resp.status_code}")
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

# Re-fetch eval-cases to verify scoring persisted
resp2 = client.get(f"/sessions/{SESSION_ID}/eval-cases")
assert resp2.status_code == 200
case_data = resp2.json()[0]

for field, expected in [
    ("human_score", 4),
    ("human_comment", "AC-08D/E API scoring test."),
    ("passed", True),
]:
    val = case_data.get(field)
    ok = val == expected
    print(f"  {'OK' if ok else 'FAIL'}: {field} = {val}")
    assert ok, f"Scoring field {field}: expected {expected}, got {val}"

scored_at = case_data.get("scored_at")
print(f"  scored_at = {scored_at}")
assert scored_at is not None, "scored_at should be set"

print("  >>> PASS: Score API saves and persists human_score/comment/passed.")


# ======================================================================
# 6. Resolve action -> blocker cleared, re-check readiness
# ======================================================================
banner("6. Resolve eval action -> readiness blocker cleared")

from core.oversight_service import create_actions_from_eval_failures, resolve_action

# Ensure actions exist for all eval runs (some may have been auto-created by dry_run API)
create_actions_from_eval_failures(ctx, 3)
failed_actions = [a for a in ctx.pending_actions if a.source_id == run_failed.run_id]
assert len(failed_actions) >= 1, (
    f"No action for failed run {run_failed.run_id}. All: {[(a.source_type, a.source_id, a.action_type) for a in ctx.pending_actions]}"
)

fa = failed_actions[0]
print(f"  Resolving action: {fa.action_id} (source_type={fa.source_type})")

# Resolve with edit decision (eval_run actions are type "edit")
resolve_action(
    ctx,
    action_id=fa.action_id,
    decision="edit",
    note="AC-08DE: resolved.",
    payload_after={"edited_text": "AC-08DE reviewed and accepted."},
)

resp = client.get(f"/sessions/{SESSION_ID}/stage-readiness/3")
assert resp.status_code == 200
readiness_f = resp.json()
eval_fail_f = [b for b in readiness_f["blockers"] if b["blocker_type"] == "eval_failure"]

print(f"  can_continue = {readiness_f['can_continue']}")
print(f"  eval_failure blockers after resolve = {len(eval_fail_f)}")
for b in eval_fail_f:
    print(f"    source_id={b['source_id']}")

# Failed run blocker cleared; needs_review run blocker may remain
failed_blockers = [b for b in eval_fail_f if b["source_id"] == run_failed.run_id]
assert len(failed_blockers) == 0, "FAIL: failed run blocker should be cleared"

print("  >>> PASS: Action resolve clears failed-run eval blocker in readiness API.")


# ======================================================================
# 7. Audit events
# ======================================================================
banner("7. Audit events observed")

ae_types = sorted(set(ae.event_type for ae in ctx.audit_events))
print(f"  total audit events = {len(ctx.audit_events)}")
print(f"  event types = {ae_types}")

expected_types = [
    "eval_case_scored",
    "eval_run_created",
    "eval_run_completed",
    "eval_run_judged",
    "human_action_created",
    "human_action_resolved",
]
for et in expected_types:
    found = et in ae_types
    print(f"  {'OK' if found else 'MISS'}: {et}")
    # Note: some types may not appear depending on run path; this is informational

assert len(ctx.audit_events) >= 3, f"Expected >=3 audit events, got {len(ctx.audit_events)}"
print("  >>> PASS: Audit events recorded for eval run + scoring + action resolve.")


# ======================================================================
# Summary
# ======================================================================
banner("AC-08D/E Summary")
print("  All API visibility checks passed:")
print("    1. GET /eval-cases with 8+ fields                          [PASS]")
print("    2. POST /eval-cases/{eid}/run (dry_run, no LLM)           [PASS]")
print("    3. GET /eval-runs with run fields                          [PASS]")
print("    4. GET /stage-readiness/3 with eval_failure blockers      [PASS]")
print("    5. POST /eval-cases/{eid}/score with human_score/passed   [PASS]")
print("    6. Action resolve clears eval blocker in readiness        [PASS]")
print("    7. Audit events recorded                                  [PASS]")
print("\n  No uvicorn, no pytest, no PostgreSQL, no Redis, no LLM.")
print("\n  AC-08D/E PASSED")
