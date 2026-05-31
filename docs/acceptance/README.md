# Acceptance Reports Index

> **Last updated:** 2026-05-30  
> **Current release / acceptance label:** `v0.8.0-beta.1-local-preview-final`

---

## Latest Acceptance — Authoritative

**Full Acceptance — PASS (2026-05-30)**

| Document | Purpose |
|----------|---------|
| [artifacts/full_acceptance_latest_minimal/](../../artifacts/full_acceptance_latest_minimal/) | **Latest acceptance evidence directory** (minimal summaries) |
| [risk_adaptive_gate_final_validation.md](risk_adaptive_gate_final_validation.md) | Risk-adaptive Stage 3 gate validation |

**Conclusion:** PASS for personal / small-team local-preview use.

**Validated in Full Acceptance:**

- Docker environment: postgres healthy, redis healthy
- ruff check / format
- compileall and version check
- 13 acceptance scripts, 707 checks
- 148 pytest tests
- API health: ok
- OpenAPI: 66,931 bytes, 61 paths
- Frontend container: running, logs clean
- Runtime logs: no Traceback / ImportError / ValidationError / RuntimeError

---

## Post-Acceptance Real E2E Validation

Real API validation was performed after Docker Final Acceptance.

| Scenario | Result | Interpretation |
|----------|--------|----------------|
| Low-risk room booking | **PASS** — Stage 0–4 complete | Confirms real DeepSeek + Tavily path works for low-risk local use. Report creation 200 after JSONB/OOM fix. |
| Low-risk reading planner | **PASS** — Stage 0–4 complete | Confirms real DeepSeek + Tavily path works for low-risk local use |
| Student management (HIGH-risk) | **EXPECTED_SAFETY_BLOCK_CONFIRMED** | HIGH-risk gate correctly blocks Stage 3→4. Not a product defect. |
| Critical-risk medication management | **SAFETY_BLOCKED_EXPECTED** — Stage 3 blocked | Correct behavior for a critical-risk medical scenario |

Evidence:

- Inline E2E reports shipped with the source package (see root-level `LIVE_E2E_*.md` files)
- Full runtime E2E logs available from internal acceptance archives (not shipped in source package)

Reports:

- [../../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md](../../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md)
- [../../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md](../../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md)

---

## Still Not Validated / Out of Scope

| Item | Status |
|------|--------|
| Report export through a real browser download flow | Optional manual check |
| Production auth / RBAC | Out of scope; target v1.0 or production-hardening milestone |
| Multi-tenant isolation | Out of scope |
| Public internet deployment | Out of scope |
| Load / concurrency testing | Out of scope |
| Production observability and alerting | Out of scope |

---

## Earlier Acceptance Reports (Historical — superseded by `artifacts/full_acceptance_latest_minimal/`)

### Docker Final Acceptance Report — Superseded

| Document | Purpose |
|----------|---------|
| [docker_final_acceptance_report.md](docker_final_acceptance_report.md) | Historical Docker acceptance (10 scripts, 615 checks, 103 pytest) |
| [docker_final_acceptance_ledger.md](docker_final_acceptance_ledger.md) | Historical acceptance ledger |

### Phase 3T Pytest Closure — Superseded

| Document | Purpose |
|----------|---------|
| [current_acceptance_closure_report.md](current_acceptance_closure_report.md) | Historical pytest-only regression closure |

### Historical: v0.6.0-alpha.8

| Document | Purpose |
|----------|---------|
| [final_acceptance_closure_summary.md](final_acceptance_closure_summary.md) | Historical AC-00 through AC-11 closure |
| [full_regression_ft01_summary.md](full_regression_ft01_summary.md) | Historical FT-01 full regression |

### Historical Individual Acceptance Scripts

| Document | Purpose |
|----------|---------|
| [ac09a_report_artifact_export_summary.md](ac09a_report_artifact_export_summary.md) | AC-09a report artifact export (historical) |
| [ac09b_fix_reports_router_testclient_summary.md](ac09b_fix_reports_router_testclient_summary.md) | AC-09b reports router TestClient fix |
| [ac09b_report_api_persistence_summary.md](ac09b_report_api_persistence_summary.md) | AC-09b report API persistence |
| [ac09c_pg_report_artifacts_persistence_summary.md](ac09c_pg_report_artifacts_persistence_summary.md) | AC-09c PostgreSQL report persistence |
| [_ac07e_evidence_safety_acceptance_summary.md](_ac07e_evidence_safety_acceptance_summary.md) | AC-07e evidence/safety |
| [_ac08e_eval_acceptance_summary.md](_ac08e_eval_acceptance_summary.md) | AC-08e eval |

Historical reports are retained for traceability only. Use the Docker Final Acceptance and current validation documents for the latest status.
