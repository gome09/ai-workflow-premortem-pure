# Real E2E Results Summary

> **Last updated:** 2026-05-31 (final delivery alignment update)
> **API keys used:** Real DeepSeek + Tavily (not dummy)

---

## Overview

After full acceptance passed, real E2E validation was performed with live API keys to confirm the platform works end-to-end for actual AI project analysis. See `artifacts/full_acceptance_latest_minimal/` for the latest acceptance evidence.

---

## Low-Risk E2E: Room Booking System

**Session:** `b0bf89e0-05ec-4d7f-807a-61b25d8a002f`
**Topic:** 企业内部会议室预约系统
**Risk Level:** LOW (internal productivity tool)
**Final Status:** **PASS**

### Stage Results

| Stage | Status | Key Outputs |
|-------|--------|-------------|
| Stage 0 (Init) | ✅ PASS | Session created, DeepSeek connected |
| Stage 1 (Failure Modes) | ✅ PASS | 8 failure modes, 5 evidence sources, Tavily search worked |
| Stage 2 (Workflow Design) | ✅ PASS | 7 workflow nodes, oversight policy inferred |
| Stage 3 (Stress Test) | ✅ PASS | 15 eval cases |
| Stage 4 (Triggers) | ✅ PASS | 11 trigger methods |
| Report Export | ✅ PASS | JSON 200, Markdown 200, Report creation 200 |

### Bugs Found & Fixed

1. **Oversight policy always None** — `stages/validators.py`, `stages/stage_2_workflow_design.py`
   - Fix: `_infer_policy_from_schema()` and `infer_oversight_policy()` always return a policy
   - Impact: Stage 2 gate no longer blocked by `policy_gap`

2. **E2E script action resolution** — `scripts/live_e2e_low_risk_room_booking.py`
   - Fix: Multi-pass action resolution; edit actions use `payload_before` as `payload_after`

3. **Report creation 500** — `storage/session_store.py`, `core/session_service.py`
   - Fix: Bounded JSONB serialization for large sessions; lightweight report context
   - Tests: 8 regression tests PASS
   - Note: The first E2E run exposed this issue; report creation was fixed from 500 to 200

### Quality Checks

| Check | Result |
|-------|--------|
| Session complete | ✅ |
| Report creation 200 | ✅ |
| JSON/Markdown export 200 | ✅ |
| Pending actions 0 | ✅ |
| New tracebacks 0 | ✅ |
| Real DeepSeek confirmed | ✅ (936 LLM traces) |
| Real Tavily confirmed | ✅ (5 evidence sources) |

**Evidence:** See inline E2E reports in project root

---

## Low-Risk E2E: Personal Reading Planner

**Session:** `ae08e110-9c31-47b4-a9c8-bf1336991a94`
**Topic:** 个人读书与学习计划管理系统
**Risk Level:** LOW (personal productivity tool)
**Final Status:** **PASS**

### Stage Results

| Stage | Status | Key Outputs |
|-------|--------|-------------|
| Stage 0 (Init) | ✅ PASS | Session created, DeepSeek connected |
| Stage 1 (Failure Modes) | ✅ PASS | 6 failure modes, 5 evidence sources, Tavily search worked |
| Stage 2 (Workflow Design) | ✅ PASS | 7 workflow nodes, DeepSeek V4 Flash |
| Stage 3 (Stress Test) | ✅ PASS | 21 eval cases (15 + 6 redteam), risk-adaptive gate applied |
| Stage 4 (Triggers) | ✅ PASS | 7 trigger methods |
| Report Export | ✅ PASS | JSON export working (bug fixed) |

### Bugs Found & Fixed

1. **EvidenceSource unhashable** — `stages/stage_1_failure_mode.py`
   - Fix: Removed `dict.fromkeys()` call
   - Tests: 3 regression tests PASS

2. **Report export IndexError** — `core/report_service.py:278`
   - Fix: `(dict.get(key) or default)[0]`
   - Tests: 7 robustness tests PASS

3. **Stage 3 gate too strict** — uniform strong gate for all projects
   - Fix: Risk-adaptive gate in `core/gates/risk_profile.py`
   - Tests: 26 tests PASS, 3 smokes PASS

### Quality Checks

| Check | Result |
|-------|--------|
| Privacy risk identified | ✅ FM2 (privacy leak) |
| Auto-delete prevention | ✅ FM4 (accidental deletion) |
| Sharing confirmation | ✅ FM5 (group report) |
| Hallucination handling | ✅ FM6 (summary hallucination) |
| Prompt injection coverage | ✅ RedTeam cases |

**Full report:** [LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md](../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md)

---

## Critical-Risk E2E: Medication Management

**Session:** `242c0d7a-56b2-4888-8848-32ce831e4871`
**Topic:** AI辅助药物管理系统
**Risk Level:** CRITICAL (healthcare/medical)
**Final Status:** **SAFETY_BLOCKED_EXPECTED_FOR_CRITICAL_RISK**

### Stage Results

| Stage | Status | Key Outputs |
|-------|--------|-------------|
| Stage 0 (Init) | ✅ PASS | Session created |
| Stage 1 (Failure Modes) | ✅ PASS | 11 evidence, 6 safety findings |
| Stage 2 (Workflow Design) | ✅ PASS | Multiple workflow nodes |
| Stage 3 (Stress Test) | ⛔ BLOCKED | 59 legitimate safety blockers |
| Stage 4 (Triggers) | ⏭️ Not reached | Blocked by Stage 3 |

### Why Stage 3 Is Blocked

This is **correct and expected** behavior:

1. **EvalCase coverage** — all high-risk workflow nodes need eval cases
2. **EvalRun review** — all eval results need human calibration
3. **RedTeam coverage** — high-risk nodes need redteam cases
4. **Action tracking** — rejected actions need proper remediation
5. **Regression detection** — new versions need better safety coverage
6. **Parser errors** — structural issues need fixing

The risk-adaptive gate correctly classifies this as **CRITICAL** tier and applies the strongest gate profile. A low-risk project with the same codebase passes Stage 3 without these blockers.

### Risk-Adaptive Gate Context

| Property | Value |
|----------|-------|
| Risk tier | CRITICAL |
| Reason | Healthcare/medical domain keywords |
| `require_redteam_coverage` | True |
| `require_eval_regression` | True |
| `require_trace_backfill` | True |
| `require_expert_review` | True |

**Full report:** [LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md](../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md)

---

## High-Risk E2E: Student Management

**Session:** `e06c0336-16b3-4ed4-bbb5-9aca458e7c9b`
**Topic:** 学生管理系统
**Risk Level:** HIGH (student PII, grade integrity, permission boundaries)
**Final Status:** **EXPECTED_SAFETY_BLOCK_CONFIRMED**

### Stage Results

| Stage | Status | Key Outputs |
|-------|--------|-------------|
| Stage 0 (Init) | ✅ PASS | Session created |
| Stage 1 (Failure Modes) | ✅ PASS | Failure modes identified, Tavily search worked |
| Stage 2 (Workflow Design) | ✅ PASS | Workflow nodes generated |
| Stage 3 (Stress Test) | ⛔ BLOCKED | 148 blockers (67 eval_failure, 8 redteam_coverage, 1 trace_backfill_gap) |
| Stage 4 (Triggers) | ⏭️ Not reached | Blocked by Stage 3 |

### Why Stage 3 Is Blocked

This is **correct and expected** behavior for a HIGH-risk scenario:

1. **Student PII/privacy** — student management involves personal information (names, IDs, enrollment records)
2. **Grade integrity** — grade modification and transcript generation require audit trails and human confirmation
3. **Permission boundaries** — role-based access (student, instructor, admin, registrar) must be validated
4. **Import/export risk** — bulk data import/export can cause mass data exposure or corruption
5. **HIGH-risk adaptive gate** — requires redteam → eval → dataset → baseline → regression. None completed.

### Fix Verification

| Check | Result |
|-------|--------|
| E2E rerun | EXPECTED_SAFETY_BLOCK_CONFIRMED |
| Export JSON | 200 |
| Export Markdown | 200 |
| Report creation | 200 |
| 422 errors | 2/299+ (edit action hash mismatch, fallback succeeded) |
| Runtime logs | No unexplained Traceback/ImportError/RuntimeError/HTTP 500 |
| API key leakage | None |
| Real DeepSeek | ✅ Confirmed |
| Real Tavily | ✅ Confirmed |

**Evidence:** See inline E2E reports in project root

**Interpretation:** This is not a FAIL. This is not a clean business-flow PASS. This is expected HIGH-risk safety-gate behavior. It does not prove production readiness.

---

## Key Takeaways

1. **The platform works end-to-end** with real DeepSeek and Tavily API calls
2. **Low-risk projects complete fully** through Stage 0–4
3. **Critical-risk projects are correctly blocked** by safety gates — this is by design
4. **The risk-adaptive gate** ensures LOW-risk projects aren't over-blocked while CRITICAL-risk projects retain strong safety
5. **All identified bugs have been fixed** with regression tests

---

## Test Results Summary

| Category | Tests | Status |
|----------|-------|--------|
| Risk-adaptive gate | 26 | PASS |
| Report export robustness | 7 | PASS |
| Stage resolution contract | 3 | PASS |
| Gate engine | 2 | PASS |
| Redteam coverage gate | 1 | PASS |
| Trace backfill gate | 3 | PASS |
| Eval regression gate | 2 | PASS |
| **Gate/export related total** | **44** | **PASS** |
| **Full pytest** | **148** | **PASS** |
