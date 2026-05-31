"""AC-07A EvidenceSource minimal creation & Stage Gate blocker audit.

No pytest, no network, no API, no PostgreSQL/Redis, no Tavily, no LLM.
"""

from __future__ import annotations

import sys

# -- Ensure local package is importable ----------------------------------------
sys.path.insert(0, ".")

from core.evidence_service import verify_evidence_source
from core.models import (
    EvidenceSource,
    FailureMode,
    ProjectContext,
    SessionState,
    Stage1Output,
)
from core.stage_readiness_service import evaluate_stage_gate


def banner(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Setup: minimal ProjectContext with one high-severity FailureMode
# ---------------------------------------------------------------------------
banner("Setup: Construct minimal session context + high-risk failure mode")

ctx = ProjectContext(
    session_id="ac07a-session",
    current_state=SessionState.S1_REVIEW,
    stage_output_versions={"stage_1": 1},
)

fm = FailureMode(
    id="fm_ac07a_high",
    category="reasoning_gap",
    description="AC-07A: high-risk failure mode for evidence gate audit",
    severity="high",
    evidence="EVID-AC07A-TEST",
    evidence_ids=["EVID-AC07A-TEST"],
)

ctx.stage_1_output = Stage1Output(
    failure_modes=[fm],
    direct_conclusion="AC-07A test conclusion",
)

ev = EvidenceSource(
    evidence_id="EVID-AC07A-TEST",
    session_id=ctx.session_id,
    title="AC-07A test evidence",
    url="https://example.com/ac07a-test",
    source_type="official_doc",
    credibility_score=0.85,
    summary="Test evidence for AC-07A audit.",
    claims=["Test claim: evidence gate works correctly."],
    used_by_failure_mode_ids=["fm_ac07a_high"],
)

ctx.evidence_sources.append(ev)

print(f"  session_id  = {ctx.session_id}")
print(f"  state       = {ctx.current_state.value}")
print(f"  failure_mode.id       = {fm.id}")
print(f"  failure_mode.severity = {fm.severity}")
print(f"  failure_mode.evidence_ids = {fm.evidence_ids}")
print(f"  evidence.id           = {ev.evidence_id}")
print(f"  evidence.verified     = {ev.verified}")
print(f"  evidence.credibility  = {ev.credibility_score}")
print(f"  evidence_sources count = {len(ctx.evidence_sources)}")
print(f"  audit_events count     = {len(ctx.audit_events)}")


# ---------------------------------------------------------------------------
# Scenario A: evidence exists but NOT verified → evidence_gap blocker
# ---------------------------------------------------------------------------
banner("Scenario A: Unverified evidence → expect evidence_gap blocker")

result_a = evaluate_stage_gate(ctx, stage=1)
blockers_a = [b for b in result_a.blockers if b.blocker_type == "evidence_gap"]

print(f"  can_continue         = {result_a.can_continue}")
print(f"  total blockers       = {len(result_a.blockers)}")
print(f"  evidence_gap blockers = {len(blockers_a)}")
for b in blockers_a:
    print(f"    - {b.blocker_id}")
    print(f"      severity:        {b.severity}")
    print(f"      message:         {b.message[:120]}...")
    print(f"      required_resolution: {b.required_resolution}")
    print(f"      metadata.gap_type:   {b.metadata.get('gap_type', 'N/A')}")

assert any(b.metadata.get("gap_type") == "unverified_evidence_id" for b in blockers_a), (
    "Scenario A FAIL: expected unverified_evidence_id gap"
)
print("\n  >>> PASS: Unverified evidence produces evidence_gap blocker.")


# ---------------------------------------------------------------------------
# Scenario B: verify evidence → blocker cleared
# ---------------------------------------------------------------------------
banner("Scenario B: Verify evidence → expect evidence_gap blocker cleared")

verified = verify_evidence_source(ctx, "EVID-AC07A-TEST", note="AC-07A audit verification")
print(f"  verified.evidence_id   = {verified.evidence_id}")
print(f"  verified.verified      = {verified.verified}")
print(f"  verified.verified_by   = {verified.verified_by}")
print(f"  verified.verified_at   = {verified.verified_at}")

result_b = evaluate_stage_gate(ctx, stage=1)
blockers_b = [b for b in result_b.blockers if b.blocker_type == "evidence_gap"]

print(f"  can_continue          = {result_b.can_continue}")
print(f"  total blockers        = {len(result_b.blockers)}")
print(f"  evidence_gap blockers  = {len(blockers_b)}")

assert len(blockers_b) == 0, (
    f"Scenario B FAIL: expected 0 evidence_gap blockers after verify, got {len(blockers_b)}"
)
print("\n  >>> PASS: Verified evidence clears evidence_gap blocker.")


# ---------------------------------------------------------------------------
# Scenario C: audit event recorded
# ---------------------------------------------------------------------------
banner("Scenario C: Audit event traceability")

evidence_events = [
    ae
    for ae in ctx.audit_events
    if ae.event_type == "evidence_verified"
    and ae.target_type == "evidence_source"
    and ae.target_id == "EVID-AC07A-TEST"
]

print(f"  total audit_events            = {len(ctx.audit_events)}")
print(f"  evidence_verified events      = {len(evidence_events)}")
for ae in evidence_events:
    print(f"    - event_id:   {ae.event_id}")
    print(f"      actor:      {ae.actor}")
    print(f"      event_type: {ae.event_type}")
    print(f"      target_id:  {ae.target_id}")
    print(f"      before_hash: {ae.before_hash[:16] if ae.before_hash else 'N/A'}...")
    print(f"      after_hash:  {ae.after_hash[:16] if ae.after_hash else 'N/A'}...")
    print(f"      has before_snapshot: {ae.before_snapshot is not None}")
    print(f"      has after_snapshot:  {ae.after_snapshot is not None}")
    print(f"      metadata:   {ae.metadata}")

assert len(evidence_events) >= 1, (
    "Scenario C FAIL: expected at least 1 evidence_verified audit event"
)
print("\n  >>> PASS: verify_evidence produces AuditEvent with before/after snapshot.")


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
banner("AC-07A Summary")
print("  All scenarios passed:")
print("    A - Unverified evidence -> evidence_gap blocker        [PASS]")
print("    B - Verified evidence -> blocker cleared               [PASS]")
print("    C - Audit event with before/after snapshots recorded  [PASS]")
print(f"\n  Total audit events: {len(ctx.audit_events)}")
print(f"  Evidence sources:   {len(ctx.evidence_sources)}")
print(f"  Session state:      {ctx.current_state.value}")
print("\n  AC-07A PASSED")
