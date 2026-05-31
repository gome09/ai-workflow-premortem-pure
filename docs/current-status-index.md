# Current Status Index

> **Last updated:** 2026-05-31 (final delivery alignment update)
> **Purpose:** Single entry point for all current, authoritative project documentation.

---


## Current Status Phrase

Use the following wording for the current package state:

> `v0.8.0-beta.1-local-preview-final` is accepted for personal and trusted small-team local-preview use. It is not production-ready and should not be deployed publicly or used as a multi-tenant service.

---

## Authoritative Documents (Current Status)

| # | Document | Purpose |
|---|----------|---------|
| 0 | [artifacts/full_acceptance_latest_minimal/](../artifacts/full_acceptance_latest_minimal/) | **Latest acceptance evidence directory** (minimal summaries) |
| 1 | [README.md](../README.md) | Project overview, quick start, current validation summary |
| 2 | [CLAUDE.md](../CLAUDE.md) | Constraints for Claude Code sessions |
| 2a | [SECURITY.md](../SECURITY.md) | Security policy and local-preview boundary |
| 3 | [docs/current_project_state.md](current_project_state.md) | **Authoritative project status** — acceptance, E2E, gate results |
| 4 | [docs/validation-status.md](validation-status.md) | All validation results in one place |
| 5 | [docs/e2e-results-summary.md](e2e-results-summary.md) | Real E2E results with live DeepSeek + Tavily |
| 6 | [docs/stage3-risk-adaptive-gate.md](stage3-risk-adaptive-gate.md) | Risk-adaptive Stage 3 gate documentation |
| 7 | [LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md](../LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md) | Low-risk reading planner E2E report (PASS) |
| 8 | [LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md](../LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md) | Critical-risk E2E report (SAFETY_BLOCKED_EXPECTED) |
| 9 | [docs/acceptance/risk_adaptive_gate_final_validation.md](acceptance/risk_adaptive_gate_final_validation.md) | Risk-adaptive gate validation report |
| 10 | [docs/acceptance/docker_final_acceptance_report.md](acceptance/docker_final_acceptance_report.md) | Docker Final Acceptance report (historical, superseded by `artifacts/full_acceptance_latest_minimal/`) |

---

## Setup & Operations

| Document | Purpose |
|----------|---------|
| [docs/startup.md](startup.md) | Startup guide — Docker, local dev, troubleshooting |
| [docs/local_setup.md](local_setup.md) | Environment setup — acceptance env, real-use env |
| [docs/acceptance/README.md](acceptance/README.md) | Acceptance reports index |

---

## Architecture & Design

| Document | Purpose |
|----------|---------|
| [docs/architecture.md](architecture.md) | Runtime path, execution modes |
| [docs/security-model.md](security-model.md) | SafetyFinding types, blocking behavior |
| [docs/stage-transition-policy.md](stage-transition-policy.md) | Stage transition rules |
| [docs/human-oversight-v0.2.md](human-oversight-v0.2.md) | Human oversight design |

---

## Version History

| Document | Purpose |
|----------|---------|
| [CHANGELOG.md](../CHANGELOG.md) | Version history |
| [ROADMAP.md](../ROADMAP.md) | Development roadmap |

---

## Superseded / Archived Documents

The following documents are historical and have been superseded. They are retained for reference only.

### Removed Raw Runtime Exports

Raw E2E export JSON/Markdown files were removed from the clean package to avoid shipping bulky runtime payloads or historical API responses. The active summarized reports remain in the repository root and `docs/acceptance/`.

### Historical Acceptance Reports (all superseded by `artifacts/full_acceptance_latest_minimal/`)

| Document | Status |
|----------|--------|
| [acceptance/docker_final_acceptance_report.md](acceptance/docker_final_acceptance_report.md) | Superseded: Docker acceptance (10 scripts, 615 checks, 103 pytest) |
| [acceptance/docker_final_acceptance_ledger.md](acceptance/docker_final_acceptance_ledger.md) | Superseded: Docker acceptance ledger |
| [acceptance/current_acceptance_closure_report.md](acceptance/current_acceptance_closure_report.md) | Superseded: Phase 3T pytest closure |
| [acceptance/final_acceptance_closure_summary.md](acceptance/final_acceptance_closure_summary.md) | Historical: v0.6.0-alpha.8 |
| [acceptance/full_regression_ft01_summary.md](acceptance/full_regression_ft01_summary.md) | Historical: v0.6.0-alpha.8 |

### Historical Design Docs

These are retained for project history. They do NOT represent current implementation state.

- `docs/v0.8.0-alpha.*` series — alpha design documents
- `docs/v0.7*` series — v0.7 design documents
- `docs/v0_6_*` series — v0.6 design documents
- `docs/v0_5_*` series — v0.5 design documents
- Historical root-level patch/link-recovery files were removed from the clean distribution; current status is captured in `CHANGELOG.md`, `ROADMAP.md`, `docs/validation-status.md`, and this index.

---

## Quick Status Summary

| Dimension | Status |
|-----------|--------|
| Docker Final Acceptance | ✅ PASS |
| Real E2E (low-risk room booking) | ✅ PASS — Stage 0–4 complete, report creation 200 |
| Real E2E (low-risk reading planner) | ✅ PASS — Stage 0–4 complete |
| Real E2E (student management) | ✅ EXPECTED_SAFETY_BLOCK — HIGH-risk gate blocked |
| Real E2E (critical-risk medication) | ✅ SAFETY_BLOCKED — expected for medical scenario |
| Risk-adaptive gate | ✅ PASS — 26/26 tests, 3 smokes |
| Report export | ✅ PASS — 7/7 tests |
| Large-session report fix | ✅ PASS — 8 regression tests |
| Bugs fixed | ✅ EvidenceSource + IndexError + gate strictness + JSONB/OOM + oversight policy |
| Full pytest | ✅ 148/148 PASS |
| **Overall** | **PASS — local-preview ready** |
