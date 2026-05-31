"""AC-07C Evidence + Safety Joint Stage Gate consistency audit.

No pytest, no network, no API, no PostgreSQL/Redis, no Tavily, no LLM.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from core.evidence_service import verify_evidence_source
from core.models import (
    EvidenceSource,
    FailureMode,
    ProjectContext,
    SafetyFinding,
    SessionState,
    Stage1Output,
)
from core.safety_service import resolve_safety_finding
from core.stage_readiness_service import evaluate_stage_gate


def banner(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def show_blockers(result, label: str) -> None:
    """Print a summary of blockers from a gate result."""
    by_type: dict[str, list] = {}
    for b in result.blockers:
        by_type.setdefault(b.blocker_type, []).append(b)

    print(
        f"\n  [{label}] can_continue={result.can_continue}, total_blockers={len(result.blockers)}"
    )
    for bt, blist in sorted(by_type.items()):
        print(f"    {bt}: {len(blist)}")
        for b in blist:
            print(f"      - {b.blocker_id}")
            print(f"        source_id: {b.source_id}")
            print(f"        required_resolution: {b.required_resolution}")


# ======================================================================
# Context 1: Both evidence unverified + safety open (stage 1)
# ======================================================================
banner("Setup Context 1: Stage 1 with unverified evidence + open safety finding")

ctx1 = ProjectContext(
    session_id="ac07c-session-1",
    current_state=SessionState.S1_REVIEW,
    stage_output_versions={"stage_1": 1},
)

# -- FailureMode (high) with evidence ref --
fm = FailureMode(
    id="fm_ac07c_high",
    category="joint_gate_test",
    description="AC-07C: high-risk failure mode for joint gate audit",
    severity="high",
    evidence="EVID-AC07C-JOINT",
    evidence_ids=["EVID-AC07C-JOINT"],
)

ctx1.stage_1_output = Stage1Output(
    failure_modes=[fm],
    direct_conclusion="AC-07C joint gate conclusion.",
)

# -- EvidenceSource (unverified) --
ev = EvidenceSource(
    evidence_id="EVID-AC07C-JOINT",
    session_id=ctx1.session_id,
    title="AC-07C Joint Gate Evidence",
    url="https://example.com/ac07c-joint",
    source_type="official_doc",
    credibility_score=0.85,
    summary="Test evidence for joint gate audit.",
    claims=["Test claim for AC-07C."],
    used_by_failure_mode_ids=["fm_ac07c_high"],
)
ctx1.evidence_sources.append(ev)

# -- SafetyFinding (open, high, stage 1) --
sf = SafetyFinding(
    finding_id="SF-AC07C-JOINT",
    session_id=ctx1.session_id,
    stage_id=1,
    risk_type="prompt_injection",
    severity="high",
    location="stage_1.test_joint",
    description="AC-07C: joint gate safety finding.",
    recommended_action="Review for potential prompt injection.",
    requires_human_review=True,
    status="open",
)
ctx1.safety_findings.append(sf)

print(f"  session_id        = {ctx1.session_id}")
print(f"  failure_mode      = {fm.id} [{fm.severity}]")
print(f"  evidence          = {ev.evidence_id} verified={ev.verified}")
print(f"  safety_finding    = {sf.finding_id} status={sf.status} severity={sf.severity}")
print(f"  audit_events init = {len(ctx1.audit_events)}")


# ======================================================================
# Scenario A: Both open -> both blocker types present, can_continue=False
# ======================================================================
banner("Scenario A: Both unverified evidence + open safety -> two blocker types")

result_a = evaluate_stage_gate(ctx1, stage=1)
show_blockers(result_a, "A")

evidence_blockers_a = [b for b in result_a.blockers if b.blocker_type == "evidence_gap"]
safety_blockers_a = [b for b in result_a.blockers if b.blocker_type == "safety_finding"]

assert not result_a.can_continue, "A FAIL: expected can_continue=False"
assert len(evidence_blockers_a) >= 1, (
    f"A FAIL: expected >=1 evidence_gap, got {len(evidence_blockers_a)}"
)
assert len(safety_blockers_a) >= 1, (
    f"A FAIL: expected >=1 safety_finding, got {len(safety_blockers_a)}"
)

ev_b = evidence_blockers_a[0]
sf_b = safety_blockers_a[0]
assert ev_b.source_id == "EVID-AC07C-JOINT", "A FAIL: evidence blocker source_id mismatch"
assert sf_b.source_id == "SF-AC07C-JOINT", "A FAIL: safety blocker source_id mismatch"
assert ev_b.required_resolution == "verify_evidence", "A FAIL: expected verify_evidence"
assert sf_b.required_resolution == "resolve_safety_finding", (
    "A FAIL: expected resolve_safety_finding"
)

print("\n  >>> PASS: Evidence gap and safety finding blockers coexist independently.")


# ======================================================================
# Scenario B: Verify evidence ONLY -> evidence cleared, safety remains
# ======================================================================
banner("Scenario B: Verify evidence only -> evidence cleared, safety remains")

verified = verify_evidence_source(ctx1, "EVID-AC07C-JOINT", note="AC-07C-joint-verify")
print(f"  evidence verified = {verified.verified}")

result_b = evaluate_stage_gate(ctx1, stage=1)
show_blockers(result_b, "B")

evidence_blockers_b = [b for b in result_b.blockers if b.blocker_type == "evidence_gap"]
safety_blockers_b = [b for b in result_b.blockers if b.blocker_type == "safety_finding"]

assert not result_b.can_continue, "B FAIL: expected can_continue=False (safety still blocks)"
assert len(evidence_blockers_b) == 0, (
    f"B FAIL: evidence_gap should be cleared after verify, got {len(evidence_blockers_b)}"
)
assert len(safety_blockers_b) >= 1, (
    f"B FAIL: safety_finding should still block, got {len(safety_blockers_b)}"
)

print("\n  >>> PASS: Verify evidence clears only evidence blocker, safety stays.")


# ======================================================================
# Scenario C: Now resolve safety -> all cleared, can_continue=True
# ======================================================================
banner("Scenario C: Resolve safety after evidence -> all clear, can_continue=True")

resolved = resolve_safety_finding(
    ctx1,
    finding_id="SF-AC07C-JOINT",
    status="resolved",
    note="AC-07C-joint-resolve",
)
print(f"  safety status = {resolved.status}")

result_c = evaluate_stage_gate(ctx1, stage=1)
show_blockers(result_c, "C")

evidence_blockers_c = [b for b in result_c.blockers if b.blocker_type == "evidence_gap"]
safety_blockers_c = [b for b in result_c.blockers if b.blocker_type == "safety_finding"]

assert result_c.can_continue, (
    f"C FAIL: expected can_continue=True, got {result_c.can_continue}, "
    f"blockers={[b.blocker_type for b in result_c.blockers]}"
)
assert len(evidence_blockers_c) == 0, (
    f"C FAIL: evidence_gap should remain 0, got {len(evidence_blockers_c)}"
)
assert len(safety_blockers_c) == 0, (
    f"C FAIL: safety_finding should be 0, got {len(safety_blockers_c)}"
)

print("\n  >>> PASS: Both resolved -> can_continue=True, gate fully open.")


# ======================================================================
# Context 2: Evidence unverified + safety open, then resolve safety FIRST
# ======================================================================
banner("Setup Context 2: Stage 1, evidence unverified + safety open")

ctx2 = ProjectContext(
    session_id="ac07c-session-2",
    current_state=SessionState.S1_REVIEW,
    stage_output_versions={"stage_1": 1},
)

fm2 = FailureMode(
    id="fm_ac07c_high_d",
    category="joint_gate_reverse",
    description="AC-07C-D: high-risk FM for reverse-order test",
    severity="high",
    evidence="EVID-AC07C-D",
    evidence_ids=["EVID-AC07C-D"],
)
ctx2.stage_1_output = Stage1Output(
    failure_modes=[fm2],
    direct_conclusion="AC-07C-D conclusion.",
)

ev2 = EvidenceSource(
    evidence_id="EVID-AC07C-D",
    session_id=ctx2.session_id,
    title="AC-07C-D Evidence",
    url="https://example.com/ac07c-d",
    source_type="official_doc",
    credibility_score=0.85,
    summary="Test evidence for reverse-order test.",
    claims=["AC-07C-D claim."],
    used_by_failure_mode_ids=["fm_ac07c_high_d"],
)
ctx2.evidence_sources.append(ev2)

sf2 = SafetyFinding(
    finding_id="SF-AC07C-D",
    session_id=ctx2.session_id,
    stage_id=1,
    risk_type="unsafe_instruction",
    severity="critical",
    location="stage_1.test_reverse",
    description="AC-07C-D: reverse-order safety finding.",
    recommended_action="Review critical unsafe instruction.",
    requires_human_review=True,
    status="open",
)
ctx2.safety_findings.append(sf2)

print(f"  failure_mode   = {fm2.id} [{fm2.severity}]")
print(f"  evidence       = {ev2.evidence_id} verified={ev2.verified}")
print(f"  safety_finding = {sf2.finding_id} status={sf2.status} severity={sf2.severity}")


# ======================================================================
# Scenario D: Resolve safety first -> safety cleared, evidence still blocks
# ======================================================================
banner("Scenario D: Resolve safety first -> evidence_gap remains, can_continue=False")

# Verify both exist initially
result_d0 = evaluate_stage_gate(ctx2, stage=1)
show_blockers(result_d0, "D-initial")
assert len([b for b in result_d0.blockers if b.blocker_type == "evidence_gap"]) >= 1
assert len([b for b in result_d0.blockers if b.blocker_type == "safety_finding"]) >= 1

# Resolve safety (dismiss, since no blocking action exists yet)
dismissed = resolve_safety_finding(
    ctx2,
    finding_id="SF-AC07C-D",
    status="dismissed",
    note="AC-07C-D: dismissed as false positive.",
)
print(f"\n  safety dismissed: status={dismissed.status}")

result_d = evaluate_stage_gate(ctx2, stage=1)
show_blockers(result_d, "D-after-dismiss")

evidence_blockers_d = [b for b in result_d.blockers if b.blocker_type == "evidence_gap"]
safety_blockers_d = [b for b in result_d.blockers if b.blocker_type == "safety_finding"]

assert not result_d.can_continue, "D FAIL: expected can_continue=False (evidence still blocks)"
assert len(safety_blockers_d) == 0, (
    f"D FAIL: safety_finding should be cleared after dismiss, got {len(safety_blockers_d)}"
)
assert len(evidence_blockers_d) >= 1, (
    f"D FAIL: evidence_gap should remain, got {len(evidence_blockers_d)}"
)
assert evidence_blockers_d[0].source_id == "EVID-AC07C-D", (
    "D FAIL: evidence blocker source_id mismatch"
)
assert evidence_blockers_d[0].required_resolution == "verify_evidence"

print("\n  >>> PASS: Resolve safety first leaves evidence blocker intact.")


# ======================================================================
# Audit events: distinct record types for evidence and safety
# ======================================================================
banner("Audit Events: Evidence vs Safety distinct record types")

# Context 1 audit events (verify_evidence + safety_finding_resolved)
ev_audit_ctx1 = [ae for ae in ctx1.audit_events if ae.event_type == "evidence_verified"]
sf_audit_ctx1 = [ae for ae in ctx1.audit_events if ae.event_type.startswith("safety_finding_")]

print(f"  Context 1 audit_events total = {len(ctx1.audit_events)}")
print(f"    evidence_verified events   = {len(ev_audit_ctx1)}")
for ae in ev_audit_ctx1:
    print(
        f"      event_id={ae.event_id} target_id={ae.target_id} "
        f"before_verified={ae.before_snapshot.get('verified') if ae.before_snapshot else 'N/A'}"
    )
print(f"    safety_finding_* events    = {len(sf_audit_ctx1)}")
for ae in sf_audit_ctx1:
    print(f"      event_id={ae.event_id} target_id={ae.target_id} event_type={ae.event_type}")

assert len(ev_audit_ctx1) >= 1, "Audit FAIL: expected >=1 evidence_verified events in ctx1"
assert len(sf_audit_ctx1) >= 1, "Audit FAIL: expected >=1 safety_finding_* events in ctx1"

# Context 2 audit events (safety_finding_dismissed, NO evidence_verified)
ev_audit_ctx2 = [ae for ae in ctx2.audit_events if ae.event_type == "evidence_verified"]
sf_audit_ctx2 = [ae for ae in ctx2.audit_events if ae.event_type.startswith("safety_finding_")]

print(f"\n  Context 2 audit_events total = {len(ctx2.audit_events)}")
print(f"    evidence_verified events   = {len(ev_audit_ctx2)}")
assert len(ev_audit_ctx2) == 0, (
    "Audit FAIL: evidence was NOT verified in ctx2, should have 0 evidence_verified events"
)
print(f"    safety_finding_* events    = {len(sf_audit_ctx2)}")
for ae in sf_audit_ctx2:
    print(f"      event_id={ae.event_id} target_id={ae.target_id} event_type={ae.event_type}")
assert len(sf_audit_ctx2) >= 1, "Audit FAIL: expected >=1 safety_finding_* events in ctx2"

print("\n  >>> PASS: Audit events are independently typed per domain (evidence vs safety).")


# ======================================================================
# Final summary
# ======================================================================
banner("AC-07C Summary")
print("  All scenarios passed:")
print("    A - evidence_gap + safety_finding coexist              [PASS]")
print("    B - verify evidence -> only evidence cleared           [PASS]")
print("    C - then resolve safety -> gate fully open             [PASS]")
print("    D - resolve safety first -> only safety cleared        [PASS]")
print("    Audit - distinct event types per domain                [PASS]")
print("\n  No blockers were overwritten or cross-contaminated.")
print("  Evidence verify and safety resolve/dismiss are independent.")
print("\n  AC-07C PASSED")
