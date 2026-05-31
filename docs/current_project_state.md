# Current Project State

> **Last updated:** 2026-05-31 (final delivery alignment update)
> **This document is the authoritative project status entry point.**
> Startup instructions: [startup.md](startup.md). Environment setup: [local_setup.md](local_setup.md).

---

## 1. Project

**Name:** AI Workflow Pre-mortem & Human Oversight Platform

**Description:** A LangGraph-based workflow engine with human oversight gates, evidence/safety/eval governance, stage advancement contracts, and report artifact generation. It guides AI project teams through four project-inception stages: failure-mode analysis, human-AI workflow design, stress/eval generation, and deployment trigger planning.

---

## 2. Version Metadata

| Source | Value |
|--------|-------|
| `pyproject.toml` version | `0.8.0-alpha.11` |
| `core/version.py` `APP_VERSION` | `0.8.0-alpha.11` |
| `core/version.py` `REPORT_SCHEMA_VERSION` | `0.8.0-alpha.11` |
| Release / acceptance label | `v0.8.0-beta.1-local-preview-final` |

The package metadata remains `0.8.0-alpha.11`. The release / acceptance label reflects the completed local-preview validation state. These are intentionally distinct.

---

## 3. Overall Status

| Dimension | Status |
|-----------|--------|
| Docker Final Local-Preview Acceptance | **PASS** |
| Real low-risk room booking E2E | **PASS** — Stage 0–4 complete, report creation 200 |
| Real low-risk reading planner E2E | **PASS** — Stage 0–4 complete |
| Real student management E2E | **EXPECTED_SAFETY_BLOCK_CONFIRMED** — HIGH-risk gate blocked |
| Real critical-risk medication mgmt E2E | **SAFETY_BLOCKED_EXPECTED** — Stage 3 correctly blocked |
| Risk-adaptive Stage 3 gate | **PASS** — 26/26 tests, 3 smokes |
| Personal / small-team local use | **READY** |
| Production / public / multi-tenant use | **NOT READY** |

---

## 4. Full Acceptance

| Phase | Result |
|-------|--------|
| Docker environment | postgres healthy, redis healthy |
| ruff check / format | PASS |
| compileall / version_check | PASS (0.8.0-alpha.11) |
| Acceptance scripts | PASS — 13 scripts, 707 checks |
| Full pytest | PASS — 148/148 |
| API /health | ok |
| OpenAPI | 66,931 bytes, 61 paths |
| Frontend container | running, logs clean |
| Runtime logs | no Traceback / ImportError / ValidationError / RuntimeError |
| **Overall** | **PASS** |

Evidence: [artifacts/full_acceptance_latest_minimal/](../artifacts/full_acceptance_latest_minimal/)

Historical reports (superseded by `artifacts/full_acceptance_latest_minimal/`):

- [acceptance/docker_final_acceptance_report.md](acceptance/docker_final_acceptance_report.md)
- [acceptance/docker_final_acceptance_ledger.md](acceptance/docker_final_acceptance_ledger.md)

---

## 5. Real E2E Validation

Real E2E validation was performed after Docker Final Acceptance with live DeepSeek and Tavily connectivity.

### Low-Risk Scenario: Room Booking System

| Item | Result |
|------|--------|
| Session | `b0bf89e0-05ec-4d7f-807a-61b25d8a002f` |
| Final status | **PASS** — Stage 0–4 complete |
| DeepSeek | Real calls confirmed (936 LLM traces) |
| Tavily | Real calls confirmed (5 evidence sources) |
| Stage 1 | 8 failure modes |
| Stage 2 | 7 workflow nodes |
| Stage 3 | 15 eval cases |
| Stage 4 | 11 triggers |
| Report creation | 200 (after JSONB/OOM fix) |
| JSON/Markdown export | 200 |
| Pending actions | 0 |
| New tracebacks | 0 |

Evidence: See inline E2E reports in project root (`LIVE_E2E_*.md`)

**Note:** The first low-risk E2E run exposed a report creation 500 caused by oversized report/session JSONB and memory pressure. The issue was fixed by bounded report/session serialization and lightweight report generation. Regression baseline is now 148/148 pytest passed.

### Low-Risk Scenario: Personal Reading Planner

| Item | Result |
|------|--------|
| Session | `ae08e110-9c31-47b4-a9c8-bf1336991a94` |
| Final status | **PASS** — Stage 0–4 complete |
| DeepSeek | Real calls succeeded |
| Tavily | Real calls succeeded |
| Stage 1 | 6 failure modes, 5 evidence sources |
| Stage 2 | 7 workflow nodes |
| Stage 3 | 21 eval cases |
| Stage 4 | 7 trigger methods |
| Report export | PASS after robustness fix |

Report: [../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md](../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md)

### High-Risk Scenario: Student Management

| Item | Result |
|------|--------|
| Session | `e06c0336-16b3-4ed4-bbb5-9aca458e7c9b` |
| Final status | **EXPECTED_SAFETY_BLOCK_CONFIRMED** |
| DeepSeek | Real calls confirmed |
| Tavily | Real calls confirmed (5 evidence sources) |
| Stage 1–2 | PASS |
| Stage 3 | Blocked — 148 blockers (67 eval_failure, 8 redteam_coverage, 1 trace_backfill_gap) |
| Export JSON/Markdown | 200 |
| Report creation | 200 |
| 422 errors | 2/299+ (edit action hash mismatch, fallback succeeded) |

Evidence: See inline E2E reports in project root (`LIVE_E2E_*.md`)

**Interpretation:** The student management scenario is classified as HIGH risk. The HIGH-risk adaptive gate requires redteam → eval → dataset → baseline → regression. None of these chains completed, so the gate correctly blocks advancement to Stage 4. This is expected safety-gate behavior, not a product defect.

### Critical-Risk Scenario: Medication Management

| Item | Result |
|------|--------|
| Session | `242c0d7a-56b2-4888-8848-32ce831e4871` |
| Final status | **SAFETY_BLOCKED_EXPECTED_FOR_CRITICAL_RISK** |
| DeepSeek | Real calls succeeded |
| Tavily | Real calls succeeded |
| Stage 1–2 | PASS |
| Stage 3 | Blocked by legitimate high-risk safety gates |
| Stage 4 | Not reached because Stage 3 correctly blocked progression |

Report: [../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md](../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md)

Interpretation: the medical scenario block is the expected safety behavior, not a product failure.

---

## 6. Fixed During Final Acceptance / E2E

| Issue | Fix | Validation |
|-------|-----|------------|
| ruff lint/import/format issues | Auto-fix and manual cleanup | Static quality PASS |
| Acceptance script Docker PYTHONPATH issue | Added `scripts/acceptance/_run_helper.py` | Acceptance scripts PASS |
| AC-09a false positive | Changed to AST-based check | Acceptance scripts PASS |
| SQL placeholder mismatch in `_sync_evidence_sources` | Corrected VALUES clause | Acceptance scripts PASS |
| AC-11a stage gate check false positive | Accepted `advance_stage_if_ready` alternative | Acceptance scripts PASS |
| `EvidenceSource` unhashable | Removed invalid `dict.fromkeys()` call | 3 regression tests PASS |
| Report export `IndexError` | Hardened empty/default list indexing | 7 robustness tests PASS |
| Stage 3 gate too strict for low-risk projects | Added risk-adaptive gate profile | 26 tests and 3 smokes PASS |
| Report creation 500 for large sessions | Bounded JSONB serialization, lightweight report context | 8 regression tests PASS, report creation 200 |
| Oversight policy always None | `_infer_policy_from_schema()` and `infer_oversight_policy()` always return policy | Low-risk E2E Stage 2 PASS |

---

## 7. Still Not Validated / Out of Scope

| Item | Current Status |
|------|----------------|
| Report export through real browser download flow | Optional manual check |
| Production auth / RBAC | Out of scope |
| Multi-tenant security | Out of scope |
| Public internet deployment | Out of scope |
| Load / concurrency testing | Out of scope |
| Docker Swarm / Kubernetes deployment | Out of scope |
| Regulated-domain production governance | Out of scope |

---

## 8. Intended Usage Boundary

**Ready for:**

- Personal local use
- 2–5 person trusted small-team internal use
- AI project pre-mortem analysis
- Failure mode identification
- Human oversight workflow design
- EvalCase draft generation
- Local JSON / Markdown report export

**Not ready for:**

- Production SaaS deployment
- Public internet deployment
- Multi-tenant enterprise use
- Unsupervised automated decisions
- Regulated medical, legal, financial, or safety-critical deployment without independent governance
- Any use requiring authentication, authorization, RBAC, rate limiting, tenant isolation, or production observability

---

## 9. Non-Production Disclaimer

This project is a **local-preview** release. It is not production-ready.

Known limitations include:

- No authentication or authorization
- No multi-tenant isolation
- No rate limiting
- No production secrets management
- No production observability or monitoring
- No load/concurrency hardening
- No public deployment support

---

## 10. Recommended Startup Path

```bash
cp .env.example .env
# Edit .env with real DeepSeek/Tavily keys and a strong POSTGRES_PASSWORD

docker compose up -d

curl http://localhost:8000/health
# Open frontend: http://localhost:8501
```

See [startup.md](startup.md) for detailed instructions.

---

## 11. Key Docs Index

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Project overview and quick start |
| [SECURITY.md](../SECURITY.md) | Security policy and deployment boundary |
| [CHANGELOG.md](../CHANGELOG.md) | Version history |
| [docs/validation-status.md](validation-status.md) | Validation status summary |
| [docs/e2e-results-summary.md](e2e-results-summary.md) | Real E2E results summary |
| [docs/current-status-index.md](current-status-index.md) | Current documentation index |
| [docs/acceptance/README.md](acceptance/README.md) | Acceptance report index |
| [docs/acceptance/docker_final_acceptance_report.md](acceptance/docker_final_acceptance_report.md) | Docker final acceptance report |
| [docs/acceptance/risk_adaptive_gate_final_validation.md](acceptance/risk_adaptive_gate_final_validation.md) | Risk-adaptive gate validation |
| [docs/stage3-risk-adaptive-gate.md](stage3-risk-adaptive-gate.md) | Risk-adaptive Stage 3 gate documentation |
| [../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md](../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md) | Low-risk E2E report |
| [../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md](../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md) | Critical-risk E2E report |

---

This document is maintained as the source of truth for current project status. Historical alpha and v0.6/v0.7 documents are retained for traceability only.
