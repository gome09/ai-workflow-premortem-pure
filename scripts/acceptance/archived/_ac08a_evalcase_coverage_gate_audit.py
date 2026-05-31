"""AC-08A EvalCase minimal creation & Stage Gate coverage blocker audit.

No pytest, no network, no API, no PostgreSQL/Redis, no LLM, no Tavily.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from core.models import (
    EvalCase,
    FailureMode,
    ProjectContext,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    WorkflowNode,
)
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
            if b.metadata:
                gap = b.metadata.get("gap_type") or b.metadata.get("target_node_id")
                print(f"      metadata.gap_type/target: {gap}")


# ======================================================================
# Setup: Context with high-risk workflow node
# ======================================================================
banner("Setup: Context with one high-risk workflow node")

ctx = ProjectContext(
    session_id="ac08a-session",
    current_state=SessionState.S3_REVIEW,
    stage_output_versions={"stage_1": 1, "stage_2": 1, "stage_3": 1},
)

# Stage 1: high-severity FailureMode
fm_high = FailureMode(
    id="fm_ac08a_high",
    category="eval_coverage_test",
    description="AC-08A: high-risk failure mode for eval coverage audit.",
    severity="high",
)
ctx.stage_1_output = Stage1Output(
    failure_modes=[fm_high],
    direct_conclusion="AC-08A test.",
)

# Stage 2: WorkflowNode that addresses the high-risk FM
node_high = WorkflowNode(
    node_id="node_ac08a_high",
    stage_name="Review Stage",
    model_assigned="deepseek-v4",
    human_action="Review and approve",
    check_criteria="Check for hallucinations",
    failure_modes_addressed=["fm_ac08a_high"],
    prompt_template="Please review the following...",
)
ctx.stage_2_output = Stage2Output(
    workflow_nodes=[node_high],
    total_stages=4,
)

# Stage 3: placeholder (avoids missing_stage_output blocker)
ctx.stage_3_output = Stage3Output(
    test_results=[],
    overall_passed=True,
)

print(f"  session_id   = {ctx.session_id}")
print(f"  state        = {ctx.current_state.value}")
print(f"  fm_high      = {fm_high.id} [{fm_high.severity}]")
print(f"  node_high    = {node_high.node_id}")
print(f"  node.failure_modes_addressed = {node_high.failure_modes_addressed}")
print(f"  eval_cases   = {len(ctx.eval_cases)}")
print(f"  eval_runs    = {len(ctx.eval_runs)}")

# Confirm _high_risk_node_ids would return node_ac08a_high
from core.stage_readiness_service import _high_risk_node_ids

hrn = _high_risk_node_ids(ctx)
print(f"  high_risk_nodes = {hrn}")
assert "node_ac08a_high" in hrn, "FAIL: node_ac08a_high must be high-risk"
print("  Verified: node_ac08a_high is correctly identified as high-risk.")


# ======================================================================
# Scenario A: No EvalCase -> eval_failure coverage blocker
# ======================================================================
banner("Scenario A: No EvalCase covering high-risk node")

result_a = evaluate_stage_gate(ctx, stage=3)
show_blockers(result_a, "A")

coverage_blockers = [
    b
    for b in result_a.blockers
    if b.blocker_type == "eval_failure"
    and b.metadata.get("gap_type") == "missing_eval_case_coverage"
]

assert not result_a.can_continue, "A FAIL: expected can_continue=False"
assert len(coverage_blockers) >= 1, (
    f"A FAIL: expected >=1 missing_eval_case_coverage blocker, got {len(coverage_blockers)}"
)
assert coverage_blockers[0].source_id == "node_ac08a_high", (
    f"A FAIL: blocker source_id expected node_ac08a_high, got {coverage_blockers[0].source_id}"
)
assert coverage_blockers[0].required_resolution == "edit_stage_output", (
    f"A FAIL: expected edit_stage_output, got {coverage_blockers[0].required_resolution}"
)

print("\n  >>> PASS: Missing EvalCase produces eval_failure coverage blocker.")


# ======================================================================
# Scenario B: Correct EvalCase -> coverage blocker cleared
# ======================================================================
banner("Scenario B: Add EvalCase targeting node_ac08a_high")

case_correct = EvalCase(
    session_id=ctx.session_id,
    stage_id=3,
    target_node_id="node_ac08a_high",
    covered_failure_mode_ids=["fm_ac08a_high"],
    scenario_type="normal",
    input_payload="Test input for AC-08A.",
    expected_behavior="Model should identify the risk.",
    pass_criteria=["Risk correctly identified"],
)
ctx.eval_cases.append(case_correct)

print(f"  eval_case.eval_id        = {case_correct.eval_id}")
print(f"  eval_case.target_node_id = {case_correct.target_node_id}")
print(f"  eval_cases count         = {len(ctx.eval_cases)}")

result_b = evaluate_stage_gate(ctx, stage=3)
show_blockers(result_b, "B")

coverage_blockers_b = [
    b
    for b in result_b.blockers
    if b.blocker_type == "eval_failure"
    and b.metadata.get("gap_type") == "missing_eval_case_coverage"
]

assert len(coverage_blockers_b) == 0, (
    f"B FAIL: expected 0 coverage blocker after adding EvalCase, got {len(coverage_blockers_b)}"
)

# Verify the EvalCase IS counted as coverage
from core.stage_readiness_service import _collect_stage3_eval_blockers

all_eval_blockers = _collect_stage3_eval_blockers(ctx)
missing_cov = [
    b for b in all_eval_blockers if b.metadata.get("gap_type") == "missing_eval_case_coverage"
]
print(f"  remaining missing_eval_case_coverage blockers: {len(missing_cov)}")
assert len(missing_cov) == 0

print("\n  >>> PASS: Correctly-targeted EvalCase clears eval coverage blocker.")


# ======================================================================
# Scenario C: Wrong-target EvalCase -> correct target still blocked
# ======================================================================
banner("Scenario C: EvalCase with wrong target_node_id, correct target still blocked")

# Fresh context for clean test
ctx2 = ProjectContext(
    session_id="ac08a-session-2",
    current_state=SessionState.S3_REVIEW,
    stage_output_versions={"stage_1": 1, "stage_2": 1, "stage_3": 1},
)

fm2 = FailureMode(
    id="fm_ac08a_c",
    category="eval_wrong_target",
    description="AC-08A-C: test wrong target EvalCase.",
    severity="critical",
)
ctx2.stage_1_output = Stage1Output(failure_modes=[fm2], direct_conclusion="test C.")

node2 = WorkflowNode(
    node_id="node_ac08a_correct_target",
    stage_name="Review",
    model_assigned="gpt-4",
    human_action="Approve",
    check_criteria="Safety check",
    failure_modes_addressed=["fm_ac08a_c"],
    prompt_template="Check...",
)
ctx2.stage_2_output = Stage2Output(workflow_nodes=[node2], total_stages=4)
ctx2.stage_3_output = Stage3Output(test_results=[], overall_passed=True)

# Confirm the node is high risk
hrn2 = _high_risk_node_ids(ctx2)
print(f"  high_risk_nodes = {hrn2}")
assert "node_ac08a_correct_target" in hrn2

# Add EvalCase with WRONG target_node_id
case_wrong = EvalCase(
    session_id=ctx2.session_id,
    target_node_id="node_ac08a_wrong_target",  # different from the actual high-risk node
    covered_failure_mode_ids=["fm_ac08a_c"],
    scenario_type="normal",
    input_payload="Wrong target test input.",
    expected_behavior="Something.",
    pass_criteria=["Some criteria."],
)
ctx2.eval_cases.append(case_wrong)

print(f"  eval_case.target_node_id = {case_wrong.target_node_id}")
print("  actual high_risk_node    = node_ac08a_correct_target")

result_c = evaluate_stage_gate(ctx2, stage=3)
show_blockers(result_c, "C")

coverage_blockers_c = [
    b
    for b in result_c.blockers
    if b.blocker_type == "eval_failure"
    and b.metadata.get("gap_type") == "missing_eval_case_coverage"
]

assert not result_c.can_continue, "C FAIL: expected can_continue=False"
assert len(coverage_blockers_c) >= 1, (
    f"C FAIL: correct target should still have coverage blocker, got {len(coverage_blockers_c)}"
)
assert coverage_blockers_c[0].source_id == "node_ac08a_correct_target", (
    f"C FAIL: blocker should reference correct target, got {coverage_blockers_c[0].source_id}"
)

print("\n  >>> PASS: Wrong-target EvalCase does NOT clear correct target's coverage blocker.")


# ======================================================================
# Summary
# ======================================================================
banner("AC-08A Summary")
print("  All scenarios passed:")
print("    A - No EvalCase -> eval_failure coverage blocker           [PASS]")
print("    B - Correct EvalCase -> coverage blocker cleared           [PASS]")
print("    C - Wrong-target EvalCase -> correct target still blocked  [PASS]")
print("\n  EvalCase model fields: eval_id, target_node_id, covered_failure_mode_ids,")
print("    scenario_type, input_payload, expected_behavior, pass_criteria, passed, ...")
print("  Stage 3 eval coverage gate: _collect_stage3_eval_blockers()")
print("  Coverage computed from: high_risk_nodes - eval_case_nodes")
print("\n  AC-08A PASSED")
