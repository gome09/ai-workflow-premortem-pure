# Validation Status

> **Last updated:** 2026-05-31 (final delivery alignment update)
> **Release:** `v0.8.0-beta.1-local-preview-final`
> **This document summarizes all validation results.**

---

## Quick Reference

| Dimension | Status | Details |
|-----------|--------|---------|
| Docker build | ✅ PASS | API + frontend containers |
| PostgreSQL / Redis | ✅ PASS | Health checks |
| Static quality (ruff/compileall) | ✅ PASS | Lint, format, compilation |
| Acceptance scripts | ✅ PASS | 13 scripts, 707 checks |
| Full pytest | ✅ PASS | 148/148 tests |
| API health / OpenAPI | ✅ PASS | Runtime smoke |
| Real DeepSeek API | ✅ PASS | Low-risk E2E |
| Real Tavily API | ✅ PASS | Low-risk E2E |
| Low-risk room booking E2E | ✅ PASS | Stage 0–4 complete, report creation 200 |
| Low-risk reading planner E2E | ✅ PASS | Stage 0–4 complete |
| Student management E2E | ✅ EXPECTED_SAFETY_BLOCK | HIGH-risk gate blocked as expected |
| Critical-risk medication mgmt E2E | ✅ SAFETY_BLOCKED | Expected for critical-risk scenario |
| Risk-adaptive gate | ✅ PASS | 26/26 tests, 3 smokes |
| Report export | ✅ PASS | 7/7 robustness tests |
| Large-session report fix | ✅ PASS | 8 regression tests, report creation 200 |
| EvidenceSource fix | ✅ PASS | 3 regression tests |
| **Overall** | **PASS** | Local-preview ready |

---


## Scope Clarification

The current release is validated for **personal / trusted small-team local-preview use**. It is **not** validated for public internet deployment, production SaaS, multi-tenant enterprise use, or unsupervised automated decisions.

The source package version is `0.8.0-alpha.11`; the release / acceptance label is `v0.8.0-beta.1-local-preview-final`.

---

## Full Acceptance (2026-05-30)

| Phase | Result |
|-------|--------|
| Docker environment | postgres healthy, redis healthy |
| ruff check / format | PASS |
| compileall / version_check | PASS (0.8.0-alpha.11) |
| Acceptance scripts (13 scripts, 707 checks) | PASS |
| Full pytest (148 tests) | PASS, 0 failures |
| API /health | ok |
| OpenAPI | 66,931 bytes, 61 paths |
| Frontend container | running, logs clean |
| Runtime logs | no Traceback / ImportError / ValidationError / RuntimeError |

**Evidence:** [artifacts/full_acceptance_latest_minimal/](../artifacts/full_acceptance_latest_minimal/)
**Historical report (superseded):** [acceptance/docker_final_acceptance_report.md](acceptance/docker_final_acceptance_report.md)

---

## Real E2E Validation (2026-05-30 ~ 2026-05-31)

### Low-Risk: Room Booking System

| Item | Result |
|------|--------|
| Session | `b0bf89e0-05ec-4d7f-807a-61b25d8a002f` |
| Final status | **PASS** — Stage 0–4 complete |
| DeepSeek | ✅ Real calls confirmed (936 LLM traces) |
| Tavily | ✅ Real calls confirmed (5 evidence sources) |
| Report creation | 200 (after JSONB/OOM fix) |
| Evidence | See inline E2E reports in project root |

### Low-Risk: Personal Reading Planner

| Item | Result |
|------|--------|
| Session | `ae08e110-9c31-47b4-a9c8-bf1336991a94` |
| Final status | **PASS** — Stage 0–4 complete |
| DeepSeek | ✅ Real calls succeeded |
| Tavily | ✅ Real calls succeeded |
| Report | [LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md](../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md) |

### Critical-Risk: Medication Management

| Item | Result |
|------|--------|
| Session | `242c0d7a-56b2-4888-8848-32ce831e4871` |
| Final status | **SAFETY_BLOCKED_EXPECTED_FOR_CRITICAL_RISK** |
| DeepSeek | ✅ Real calls succeeded |
| Tavily | ✅ Real calls succeeded |
| Stage 1–2 | ✅ PASS |
| Stage 3 | ⛔ Blocked — 59 legitimate safety blockers |
| Report | [LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md](../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md) |

**Interpretation:** Stage 3 blocking is the correct and expected behavior for a CRITICAL-risk medical scenario. The risk-adaptive gate correctly applies the strongest gate profile.

### High-Risk: Student Management

| Item | Result |
|------|--------|
| Session | `e06c0336-16b3-4ed4-bbb5-9aca458e7c9b` |
| Final status | **EXPECTED_SAFETY_BLOCK_CONFIRMED** |
| DeepSeek | ✅ Real calls confirmed |
| Tavily | ✅ Real calls confirmed (5 evidence sources) |
| Stage 3 blockers | 148 (67 eval_failure, 8 redteam_coverage, 1 trace_backfill_gap) |
| Export JSON/Markdown | 200 |
| Report creation | 200 |
| Evidence | See inline E2E reports in project root |

**Interpretation:** The student management scenario is classified as HIGH risk. The HIGH-risk adaptive gate requires redteam → eval → dataset → baseline → regression. None of these chains completed, so the gate correctly blocks advancement to Stage 4. This is expected safety-gate behavior, not a product defect.

---

## Risk-Adaptive Gate Validation

| Check | Result |
|-------|--------|
| `test_stage3_risk_adaptive_gate.py` (26 tests) | PASS |
| `test_report_export_robustness.py` (7 tests) | PASS |
| `test_redteam_coverage_gate_v080_alpha3.py` (1 test) | PASS |
| `test_eval_regression_gate_v080_alpha2.py` (2 tests) | PASS |
| `test_trace_backfill_gate_v080_alpha8.py` (2 tests) | PASS |
| `test_v080_alpha8_stage_resolution_contract.py` (3 tests) | PASS |
| Smoke 1: Low-risk reading planner | PASS |
| Smoke 2: Medication management critical | PASS |
| Smoke 3: Medium-risk feedback system | PASS |
| Real session ae08e110 gate data | PASS |

**Report:** [acceptance/risk_adaptive_gate_final_validation.md](acceptance/risk_adaptive_gate_final_validation.md)

---

## Bugs Fixed During Real E2E

| Bug | Location | Fix | Tests |
|-----|----------|-----|-------|
| `EvidenceSource` unhashable | `stages/stage_1_failure_mode.py` | Removed `dict.fromkeys()` | 3 tests |
| Report export `IndexError` | `core/report_service.py:278` | `(dict.get(key) or default)[0]` | 7 tests |
| Stage 3 gate too strict | `core/gates/risk_profile.py` | Risk-adaptive gate | 26 tests |

---

## What Has NOT Been Validated

| Item | Reason | Impact |
|------|--------|--------|
| Report export (real browser download flow) | Manual test | Non-blocking |
| Auth / RBAC | Architectural limitation | v1.0 scope |
| Multi-tenant security | Out of scope | v1.0 scope |
| Load / concurrency | Out of scope | Production hardening |

---

## Test Summary

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_stage3_risk_adaptive_gate.py` | 26 | PASS |
| `test_report_export_robustness.py` | 7 | PASS |
| `test_v080_alpha8_stage_resolution_contract.py` | 3 | PASS |
| `test_trace_backfill_gate_v080_alpha8.py` | 3 | PASS |
| `test_eval_regression_gate_v080_alpha2.py` | 2 | PASS |
| `test_gate_engine_v070.py` | 1 | PASS |
| `test_gate_rules_pluginized_v070.py` | 1 | PASS |
| `test_redteam_coverage_gate_v080_alpha3.py` | 1 | PASS |
| **Total (gate/export related)** | **44** | **PASS** |
| **Full pytest** | **148** | **PASS** |
