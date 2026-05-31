"""AC-08B/C EvalRun execution + human scoring + blocker/action audit.

No pytest, no network, no API, no PostgreSQL/Redis, no LLM, no Tavily.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from core.eval_runner import run_eval_case
from core.eval_service import score_eval_case
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
from core.oversight_service import create_actions_from_eval_failures, resolve_action
from core.stage_readiness_service import evaluate_stage_gate


def banner(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def show_blockers(result, label: str) -> None:
    by_type: dict[str, list] = {}
    for b in result.blockers:
        by_type.setdefault(b.blocker_type, []).append(b)
    print(
        f"\n  [{label}] can_continue={result.can_continue}, total_blockers={len(result.blockers)}"
    )
    for bt, blist in sorted(by_type.items()):
        print(f"    {bt}: {len(blist)}")
        for b in blist:
            print(f"      blocker_id: {b.blocker_id}")
            print(f"      source_id:  {b.source_id}")
            print(f"      required_resolution: {b.required_resolution}")
            g = (
                b.metadata.get("gap_type")
                or b.metadata.get("judge_result")
                or b.metadata.get("target_node_id")
            )
            print(f"      detail: {g}")


# ======================================================================
# Setup: Context with high-risk node + EvalCase
# ======================================================================
banner("Setup: High-risk node + EvalCase for Stage 3")

ctx = ProjectContext(
    session_id="ac08bc-session",
    current_state=SessionState.S3_REVIEW,
    stage_output_versions={"stage_1": 1, "stage_2": 1, "stage_3": 1},
)

fm = FailureMode(
    id="fm_ac08bc_high",
    category="eval_run_test",
    description="AC-08BC: high-risk FM for EvalRun + scoring audit.",
    severity="high",
)
ctx.stage_1_output = Stage1Output(failure_modes=[fm], direct_conclusion="AC-08BC test.")

node = WorkflowNode(
    node_id="node_ac08bc_high",
    stage_name="Review Stage",
    model_assigned="deepseek-v4",
    human_action="Review and approve",
    check_criteria="Check for hallucinations",
    failure_modes_addressed=["fm_ac08bc_high"],
    prompt_template="Please review the following content...",
)
ctx.stage_2_output = Stage2Output(workflow_nodes=[node], total_stages=4)
ctx.stage_3_output = Stage3Output(test_results=[], overall_passed=True)

# Create an EvalCase targeting the high-risk node
case = EvalCase(
    session_id=ctx.session_id,
    stage_id=3,
    target_node_id="node_ac08bc_high",
    covered_failure_mode_ids=["fm_ac08bc_high"],
    scenario_type="normal",
    input_payload="Test input for AC-08BC eval run audit.",
    expected_behavior="Model should correctly identify risks in the content.",
    pass_criteria=["Risk correctly identified", "No hallucinations"],
)
ctx.eval_cases.append(case)

print(f"  session_id   = {ctx.session_id}")
print(f"  fm           = {fm.id} [{fm.severity}]")
print(f"  node         = {node.node_id}")
print(f"  eval_case    = {case.eval_id}")
print(f"  target_node  = {case.target_node_id}")


# ======================================================================
# Scenario A: Run single EvalCase in manual mode -> EvalRun created
# ======================================================================
banner("Scenario A: Run EvalCase (manual mode) -> EvalRun with all fields")

run_manual = run_eval_case(ctx, eval_id=case.eval_id, run_mode="manual")

print("  EvalRun created:")
print(f"    run_id        = {run_manual.run_id}")
print(f"    eval_id       = {run_manual.eval_id}")
print(f"    target_node_id = {run_manual.target_node_id}")
print(f"    status        = {run_manual.status}")
print(f"    judge_mode    = {run_manual.judge_mode}")
print(f"    judge_result  = {run_manual.judge_result}")
print(f"    judge_reason  = {run_manual.judge_reason}")
print(f"    run_mode      = {run_manual.run_mode}")
print(f"    input_payload[:50] = {run_manual.input_payload[:50]}...")
print(f"    pass_criteria = {run_manual.pass_criteria}")

assert run_manual.run_id.startswith("RUN-"), "A FAIL: missing run_id"
assert run_manual.eval_id == case.eval_id, "A FAIL: wrong eval_id"
assert run_manual.target_node_id == "node_ac08bc_high", "A FAIL: wrong target_node_id"
assert run_manual.status == "completed", f"A FAIL: expected completed, got {run_manual.status}"
assert run_manual.judge_result == "needs_review", (
    f"A FAIL: expected needs_review, got {run_manual.judge_result}"
)
assert run_manual.judge_mode == "human", f"A FAIL: expected human, got {run_manual.judge_mode}"
assert len(ctx.eval_runs) == 1, f"A FAIL: expected 1 eval run, got {len(ctx.eval_runs)}"

print("\n  >>> PASS: Manual EvalRun created with all required fields.")


# ======================================================================
# Scenario B: EvalRun with judge_result="failed" -> eval_failure blocker
# ======================================================================
banner("Scenario B: EvalRun judge_result=failed -> eval_failure blocker")

# Construct a failed EvalRun directly (no LLM execution)
run_failed = EvalRun(
    session_id=ctx.session_id,
    eval_id=case.eval_id,
    target_node_id="node_ac08bc_high",
    covered_failure_mode_ids=["fm_ac08bc_high"],
    run_mode="dry_run",
    input_payload=case.input_payload,
    expected_behavior=case.expected_behavior,
    pass_criteria=case.pass_criteria,
    judge_result="failed",
    judge_mode="rule",
    judge_reason="AC-08BC: synthetic failed run for blocker test.",
    status="completed",
)
ctx.eval_runs.append(run_failed)

# Now call create_actions_from_eval_failures to generate actions for these runs
actions = create_actions_from_eval_failures(ctx, 3)
print(f"  pending_actions created = {len(actions)}")
for a in actions:
    print(
        f"    action_id={a.action_id} type={a.action_type} "
        f"source_type={a.source_type} source_id={a.source_id} blocking={a.blocking}"
    )

result_b = evaluate_stage_gate(ctx, stage=3)
show_blockers(result_b, "B")

eval_fail_blockers = [b for b in result_b.blockers if b.blocker_type == "eval_failure"]
assert not result_b.can_continue, "B FAIL: expected can_continue=False"
assert len(eval_fail_blockers) >= 2, (
    f"B FAIL: expected >=2 eval_failure blockers (failed + needs_review), got {len(eval_fail_blockers)}"
)

# Verify distinct blocker types: one for failed run, one for needs_review run
failed_blockers = [
    b for b in eval_fail_blockers if b.source_id in {run_failed.run_id, run_manual.run_id}
]
print(f"  eval_failure blockers total: {len(eval_fail_blockers)}")
for b in eval_fail_blockers:
    print(f"    source_id={b.source_id}")

assert len(failed_blockers) >= 2, f"B FAIL: expected >=2 eval blockers, got {len(failed_blockers)}"

print("\n  >>> PASS: Failed + needs_review EvalRuns both produce eval_failure blockers.")


# ======================================================================
# Scenario C: needs_review run -> eval_failure blocker (verified in B)
# ======================================================================
banner("Scenario C: needs_review run confirmed as eval_failure blocker")

needs_review_blockers = [b for b in eval_fail_blockers if b.source_id == run_manual.run_id]
assert len(needs_review_blockers) >= 1, (
    f"C FAIL: expected needs_review run to produce blocker, got {len(needs_review_blockers)}"
)
for b in needs_review_blockers:
    print(f"  blocker_id={b.blocker_id}")
    print(f"  source_id={b.source_id} (manual run, needs_review)")
    print(f"  severity={b.severity}")
    print(f"  required_resolution={b.required_resolution}")

print("\n  >>> PASS: needs_review run correctly produces eval_failure blocker.")


# ======================================================================
# Scenario D: PendingHumanAction generation from eval failures
# ======================================================================
banner("Scenario D: PendingHumanAction generated for failed + needs_review evals")

all_actions = ctx.pending_actions
eval_actions = [a for a in all_actions if a.source_type in {"eval_run", "eval_case"}]
print(f"  total pending_actions   = {len(all_actions)}")
print(f"  eval_run/eval_case actions = {len(eval_actions)}")
for a in eval_actions:
    print(f"    action_id={a.action_id}")
    print(f"    source_type={a.source_type}  source_id={a.source_id}")
    print(f"    action_type={a.action_type}  blocking={a.blocking}")
    print(f"    risk_level={a.risk_level}  title={a.title[:60]}")

assert len(eval_actions) >= 2, (
    f"D FAIL: expected >=2 eval actions (failed + needs_review), got {len(eval_actions)}"
)

# Check one action links to the failed run
failed_actions = [a for a in eval_actions if a.source_id == run_failed.run_id]
needs_review_actions = [a for a in eval_actions if a.source_id == run_manual.run_id]

assert len(failed_actions) >= 1, "D FAIL: no action for failed run"
assert len(needs_review_actions) >= 1, "D FAIL: no action for needs_review run"
assert failed_actions[0].blocking is True, "D FAIL: failed run action should be blocking"
assert needs_review_actions[0].blocking is True, "D FAIL: needs_review action should be blocking"

print("\n  >>> PASS: Both failed and needs_review runs generate blocking PendingHumanActions.")


# ======================================================================
# Scenario E: Human scoring -> save + audit event
# ======================================================================
banner("Scenario E: Human scoring saves + writes audit event")

audit_before = len(ctx.audit_events)

scored = score_eval_case(
    ctx,
    eval_id=case.eval_id,
    human_score=4,
    human_comment="AC-08BC manual review: output looks correct.",
    passed=True,
)

print("  EvalCase after scoring:")
print(f"    eval_id       = {scored.eval_id}")
print(f"    human_score   = {scored.human_score}")
print(f"    human_comment = {scored.human_comment}")
print(f"    passed        = {scored.passed}")
print(f"    scored_at     = {scored.scored_at}")

assert scored.human_score == 4, f"E FAIL: human_score expected 4, got {scored.human_score}"
assert scored.human_comment.startswith("AC-08BC"), "E FAIL: human_comment not saved"
assert scored.passed is True, f"E FAIL: passed expected True, got {scored.passed}"
assert scored.scored_at is not None, "E FAIL: scored_at not set"

# Check audit event
audit_after = len(ctx.audit_events)
new_events = ctx.audit_events[audit_before:]
scored_events = [ae for ae in new_events if ae.event_type == "eval_case_scored"]
print(f"\n  new audit events = {len(new_events)}")
print(f"  eval_case_scored events = {len(scored_events)}")
for ae in scored_events:
    print(f"    event_id={ae.event_id} target_id={ae.target_id}")
    print(f"    metadata={ae.metadata}")

assert len(scored_events) >= 1, "E FAIL: expected eval_case_scored audit event"

print("\n  >>> PASS: Human scoring saves fields and writes eval_case_scored audit event.")


# ======================================================================
# Scenario F: Resolve action -> eval blocker cleared
# ======================================================================
banner("Scenario F: Resolve failed-run action -> blocker cleared for that run")

# Resolve the action for the failed run
failed_action = failed_actions[0]
print(
    f"  Before resolve: pending_actions={len([a for a in ctx.pending_actions if a.status == 'pending'])}"
)
print(f"  Resolving action: {failed_action.action_id} (source_type={failed_action.source_type})")

# eval_run actions have action_type="edit" (for high-risk FM), so resolve with
# decision="edit" + payload_after (not in STRUCTURED_EDIT_SOURCE_TYPES, so
# minimal payload is accepted).
resolved_action = resolve_action(
    ctx,
    action_id=failed_action.action_id,
    decision="edit",
    note="AC-08BC: resolved after review.",
    payload_after={"edited_text": "AC-08BC reviewed and accepted."},
)

print(
    f"  After resolve: action_status={resolved_action.status} "
    f"decision={resolved_action.reviewer_decision}"
)

result_f = evaluate_stage_gate(ctx, stage=3)
show_blockers(result_f, "F")

# The failed run's blocker should be gone, but needs_review run's blocker should remain
eval_fail_blockers_f = [b for b in result_f.blockers if b.blocker_type == "eval_failure"]
print(f"\n  remaining eval_failure blockers = {len(eval_fail_blockers_f)}")
for b in eval_fail_blockers_f:
    print(f"    source_id={b.source_id}")

# Check: failed run blocker is gone
failed_run_blockers = [b for b in eval_fail_blockers_f if b.source_id == run_failed.run_id]
assert len(failed_run_blockers) == 0, (
    f"F FAIL: failed run blocker should be cleared after action resolve, "
    f"got {len(failed_run_blockers)}"
)

# Check: needs_review run blocker still exists (action not yet resolved)
needs_review_blockers_f = [b for b in eval_fail_blockers_f if b.source_id == run_manual.run_id]
assert len(needs_review_blockers_f) >= 1, (
    f"F FAIL: needs_review run blocker should still exist, got {len(needs_review_blockers_f)}"
)

# Check: can_continue is still False (needs_review blocker remains)
assert not result_f.can_continue, "F FAIL: needs_review still blocks"

print("\n  >>> PASS: Action resolve clears failed-run blocker; needs_review blocker remains.")


# ======================================================================
# Summary
# ======================================================================
banner("AC-08B/C Summary")
print("  All scenarios passed:")
print("    A - Manual EvalRun created with all fields              [PASS]")
print("    B - judge_result=failed -> eval_failure blocker         [PASS]")
print("    C - judge_result=needs_review -> eval_failure blocker   [PASS]")
print("    D - Failed/needs_review -> blocking PendingHumanAction  [PASS]")
print("    E - Human scoring saves + eval_case_scored audit        [PASS]")
print("    F - Action resolve clears failed-run eval blocker       [PASS]")
print(f"\n  Total eval_runs:     {len(ctx.eval_runs)}")
print(f"  Total audit_events:  {len(ctx.audit_events)}")
print(f"  Audit event types:   {sorted(set(ae.event_type for ae in ctx.audit_events))}")
print("  No LLM, no network, no DB, no pytest, no uvicorn.")
print("\n  AC-08B/C PASSED")
