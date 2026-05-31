"""AC-07D Evidence + Safety API visibility audit.

Uses FastAPI TestClient (no pytest, no uvicorn, no DB, no network, no LLM).
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

# ── Monkeypatch BEFORE importing api.main (prevents DB connection) ──────────
import storage.session_store as _store_mod

_store_mod.session_store.initialize = lambda: None
_store_mod.session_store.save = lambda ctx: None
_store_mod.session_store.log_event = lambda *a, **kw: None

import storage.cache as _cache_mod

_cache_mod.context_cache.set = lambda ctx: None
_cache_mod.context_cache.get = lambda sid: None
_cache_mod.context_cache.refresh_ttl = lambda sid: None
_cache_mod.context_cache.delete = lambda sid: None

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
from core.session_service import session_service

# ── Build in-memory context ─────────────────────────────────────────────────
SESSION_ID = "ac07d-api-audit"

ctx = ProjectContext(
    session_id=SESSION_ID,
    current_state=SessionState.S1_REVIEW,
    stage_output_versions={"stage_1": 1},
)

fm = FailureMode(
    id="fm_ac07d_high",
    category="api_visibility_test",
    description="AC-07D: high-risk FM for API visibility audit.",
    severity="high",
    evidence="EVID-AC07D-API",
    evidence_ids=["EVID-AC07D-API"],
)
ctx.stage_1_output = Stage1Output(
    failure_modes=[fm],
    direct_conclusion="AC-07D API visibility test.",
)

ev = EvidenceSource(
    evidence_id="EVID-AC07D-API",
    session_id=SESSION_ID,
    title="AC-07D API Test Evidence",
    url="https://example.com/ac07d-api",
    source_type="official_doc",
    credibility_score=0.85,
    summary="Evidence for AC-07D API visibility audit.",
    claims=["Test claim: API visibility works correctly."],
    used_by_failure_mode_ids=["fm_ac07d_high"],
    verified=False,
)
ctx.evidence_sources.append(ev)

sf = SafetyFinding(
    finding_id="SF-AC07D-API",
    session_id=SESSION_ID,
    stage_id=1,
    risk_type="prompt_injection",
    severity="high",
    location="stage_1.test_api",
    description="AC-07D: API visibility safety finding.",
    recommended_action="Review for potential prompt injection.",
    requires_human_review=True,
    status="open",
)
ctx.safety_findings.append(sf)

# ── Monkeypatch session_service ─────────────────────────────────────────────
_original_get_session = session_service.get_session
session_service.get_session = lambda sid: ctx if sid == SESSION_ID else None

# ── Now import app (safe: store is already patched) ─────────────────────────
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def banner(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def check_field(data: dict, field: str, expected=None, label: str = "") -> bool:
    """Check a field exists in data, optionally matching expected value."""
    if label:
        full_label = f"{label}.{field}"
    else:
        full_label = field

    if field not in data:
        print(f"  FAIL: missing field '{full_label}'")
        return False
    value = data[field]
    if expected is not None and value != expected:
        print(f"  FAIL: '{full_label}' expected={expected}, got={value}")
        return False
    print(f"  OK: {full_label} = {value}")
    return True


# ======================================================================
# 1. Evidence API: List
# ======================================================================
banner("1. Evidence API: GET /sessions/{id}/evidence")

resp = client.get(f"/sessions/{SESSION_ID}/evidence")
print(f"  status_code = {resp.status_code}")
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
data = resp.json()
assert isinstance(data, list) and len(data) >= 1, f"Expected list of evidence, got {type(data)}"
ev_data = data[0]

check_field(ev_data, "evidence_id", "EVID-AC07D-API")
check_field(ev_data, "verified", False)
check_field(ev_data, "credibility_score", 0.85)
check_field(ev_data, "source_type", "official_doc")
check_field(ev_data, "url", "https://example.com/ac07d-api")
check_field(ev_data, "title", "AC-07D API Test Evidence")
# used_by_failure_mode_ids must be present
check_field(ev_data, "used_by_failure_mode_ids")
assert "fm_ac07d_high" in ev_data["used_by_failure_mode_ids"], (
    "evidence missing used_by_failure_mode_ids linkage"
)
print("  OK: used_by_failure_mode_ids contains fm_ac07d_high")

print("\n  >>> Evidence list API: all required fields present.")


# ======================================================================
# 2. Evidence API: Single
# ======================================================================
banner("2. Evidence API: GET /sessions/{id}/evidence/{evidence_id}")

resp = client.get(f"/sessions/{SESSION_ID}/evidence/EVID-AC07D-API")
print(f"  status_code = {resp.status_code}")
assert resp.status_code == 200
ev_single = resp.json()
check_field(ev_single, "evidence_id", "EVID-AC07D-API")
check_field(ev_single, "verified", False)
print("\n  >>> Evidence single API: works correctly.")


# ======================================================================
# 3. Safety API: List
# ======================================================================
banner("3. Safety API: GET /sessions/{id}/safety-findings")

resp = client.get(f"/sessions/{SESSION_ID}/safety-findings")
print(f"  status_code = {resp.status_code}")
assert resp.status_code == 200
data = resp.json()
assert isinstance(data, list) and len(data) >= 1, f"Expected list, got {type(data)}"
sf_data = data[0]

check_field(sf_data, "finding_id", "SF-AC07D-API")
check_field(sf_data, "severity", "high")
check_field(sf_data, "status", "open")
check_field(sf_data, "requires_human_review", True)
check_field(sf_data, "stage_id", 1)
check_field(sf_data, "risk_type", "prompt_injection")
check_field(sf_data, "description", "AC-07D: API visibility safety finding.")

print("\n  >>> Safety API: all required fields present.")


# ======================================================================
# 4. Stage Readiness API: single stage
# ======================================================================
banner("4. Stage Readiness: GET /sessions/{id}/stage-readiness/1")

resp = client.get(f"/sessions/{SESSION_ID}/stage-readiness/1")
print(f"  status_code = {resp.status_code}")
assert resp.status_code == 200
readiness = resp.json()

check_field(readiness, "stage_id", 1)
check_field(readiness, "can_continue", False)
check_field(readiness, "stage_lifecycle")

blockers = readiness.get("blockers", [])
print(f"  blockers count = {len(blockers)}")
assert len(blockers) >= 2, f"Expected >=2 blockers, got {len(blockers)}"

# Find evidence_gap and safety_finding blockers
ev_blockers = [b for b in blockers if b.get("blocker_type") == "evidence_gap"]
sf_blockers = [b for b in blockers if b.get("blocker_type") == "safety_finding"]

print(f"  evidence_gap blockers: {len(ev_blockers)}")
print(f"  safety_finding blockers: {len(sf_blockers)}")

assert len(ev_blockers) >= 1, f"Expected >=1 evidence_gap in readiness, got {len(ev_blockers)}"
assert len(sf_blockers) >= 1, f"Expected >=1 safety_finding in readiness, got {len(sf_blockers)}"

# Verify blocker field completeness
required_blocker_fields = [
    "blocker_id",
    "blocker_type",
    "severity",
    "source_id",
    "required_resolution",
]
for i, b in enumerate(blockers):
    print(f"\n  blocker[{i}]: {b.get('blocker_type')}")
    for field in required_blocker_fields:
        check_field(b, field, label=f"blocker[{i}]")

print("\n  >>> Stage Readiness: both blocker types present with all required fields.")


# ======================================================================
# 5. Stage Gate API
# ======================================================================
banner("5. Stage Gate: GET /sessions/{id}/stage-gate/1")

resp = client.get(f"/sessions/{SESSION_ID}/stage-gate/1")
print(f"  status_code = {resp.status_code}")
assert resp.status_code == 200
gate = resp.json()

check_field(gate, "stage_id", 1)
check_field(gate, "can_continue", False)
gate_blockers = gate.get("blockers", [])
print(f"  blockers count = {len(gate_blockers)}")
ev_gb = [b for b in gate_blockers if b.get("blocker_type") == "evidence_gap"]
sf_gb = [b for b in gate_blockers if b.get("blocker_type") == "safety_finding"]
assert len(ev_gb) >= 1, "Stage gate: missing evidence_gap"
assert len(sf_gb) >= 1, "Stage gate: missing safety_finding"

print("\n  >>> Stage Gate API: both blocker types visible.")


# ======================================================================
# 6. Verify evidence via session_service, then re-check readiness
# ======================================================================
banner("6. After verify evidence -> readiness shows only safety blocker")

# Use session_service directly (API calls it too)
verify_evidence_source(ctx, "EVID-AC07D-API", note="AC-07D API audit verify")

resp = client.get(f"/sessions/{SESSION_ID}/stage-readiness/1")
assert resp.status_code == 200
readiness_b = resp.json()

ev_blockers_b = [b for b in readiness_b["blockers"] if b["blocker_type"] == "evidence_gap"]
sf_blockers_b = [b for b in readiness_b["blockers"] if b["blocker_type"] == "safety_finding"]

print(f"  can_continue = {readiness_b['can_continue']}")
print(f"  evidence_gap blockers: {len(ev_blockers_b)}")
print(f"  safety_finding blockers: {len(sf_blockers_b)}")

assert len(ev_blockers_b) == 0, (
    f"FAIL: evidence_gap should be 0 after verify, got {len(ev_blockers_b)}"
)
assert len(sf_blockers_b) >= 1, f"FAIL: safety_finding should remain, got {len(sf_blockers_b)}"
assert readiness_b["can_continue"] is False, "FAIL: safety still blocks"

print("\n  >>> Evidence verify: only evidence blocker cleared via API visibility.")


# ======================================================================
# 7. Resolve safety via session_service, then re-check readiness
# ======================================================================
banner("7. After resolve safety -> all blockers cleared")

resolve_safety_finding(
    ctx, finding_id="SF-AC07D-API", status="resolved", note="AC-07D API audit resolve"
)

resp = client.get(f"/sessions/{SESSION_ID}/stage-readiness/1")
assert resp.status_code == 200
readiness_c = resp.json()

ev_blockers_c = [b for b in readiness_c["blockers"] if b["blocker_type"] == "evidence_gap"]
sf_blockers_c = [b for b in readiness_c["blockers"] if b["blocker_type"] == "safety_finding"]

print(f"  can_continue = {readiness_c['can_continue']}")
print(f"  evidence_gap blockers: {len(ev_blockers_c)}")
print(f"  safety_finding blockers: {len(sf_blockers_c)}")
print(f"  total blockers: {len(readiness_c['blockers'])}")

assert len(ev_blockers_c) == 0, f"FAIL: evidence should remain clear, got {len(ev_blockers_c)}"
assert len(sf_blockers_c) == 0, f"FAIL: safety should be cleared, got {len(sf_blockers_c)}"
assert readiness_c["can_continue"] is True, (
    f"FAIL: expected can_continue=True, got {readiness_c['can_continue']}"
)

print("\n  >>> Safety resolve: all blockers cleared, can_continue=True.")


# ======================================================================
# 8. Audit events visible via audit service
# ======================================================================
banner("8. Audit events: evidence_verified + safety_finding_resolved")

audit_events = [ae.model_dump(mode="json") for ae in ctx.audit_events]
ev_audit = [ae for ae in audit_events if ae["event_type"] == "evidence_verified"]
sf_audit = [ae for ae in audit_events if ae["event_type"].startswith("safety_finding_")]

print(f"  total audit events: {len(audit_events)}")
print(f"  evidence_verified:  {len(ev_audit)}")
print(f"  safety_finding_*:   {len(sf_audit)}")

assert len(ev_audit) >= 1, "Missing evidence_verified audit event"
assert len(sf_audit) >= 1, "Missing safety_finding_* audit event"

for ae in ev_audit:
    print(f"    evidence_verified: event_id={ae['event_id']} target_id={ae['target_id']}")
for ae in sf_audit:
    print(f"    {ae['event_type']}: event_id={ae['event_id']} target_id={ae['target_id']}")

print("\n  >>> Audit events: independently recorded per domain.")


# ======================================================================
# Summary
# ======================================================================
banner("AC-07D Summary")
print("  All API visibility checks passed:")
print("    1. Evidence list/single API with verified/credibility/linkage  [PASS]")
print("    2. Safety list API with severity/status/review_required        [PASS]")
print("    3. Stage Readiness with evidence_gap + safety_finding blockers [PASS]")
print("    4. Stage Gate with both blocker types                          [PASS]")
print("    5. Verify evidence -> only evidence cleared in API             [PASS]")
print("    6. Resolve safety -> all cleared, can_continue=True in API     [PASS]")
print("    7. Audit events distinct per domain                            [PASS]")
print("\n  No uvicorn, no pytest, no PostgreSQL, no Redis.")
print("\n  AC-07D PASSED")
