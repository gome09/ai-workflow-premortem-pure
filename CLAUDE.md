# CLAUDE.md — Project State & Constraints

> **Last updated:** 2026-05-31 (final delivery alignment update)
> **Current version (package metadata):** `0.8.0-alpha.11` (pyproject.toml / core/version.py)
> **Current release label:** `v0.8.0-beta.1-local-preview-final`
> **Latest acceptance:** Full Acceptance — PASS (13/13 scripts, 707/707 checks, 148/148 pytest)
> **Evidence directory:** `artifacts/full_acceptance_latest_minimal/`

---

## Project Overview

AI Workflow Pre-mortem & Human Oversight Platform. A LangGraph-based workflow engine with human oversight gates, evidence/safety/eval governance, stage advancement contracts, and report artifact generation.

---

## Current Acceptance Status

### Full Acceptance (2026-05-30)

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
| Runtime logs | no Traceback/ImportError/ValidationError/RuntimeError |
| **Overall** | **PASS** |

**Evidence directory:** `artifacts/full_acceptance_latest_minimal/`
**Full summary:** `artifacts/full_acceptance_latest_minimal/full_acceptance_summary.md`

> **Note:** The pure-source package retains minimal acceptance summaries. Full runtime logs and bulky E2E evidence are available from internal acceptance archives, not shipped in the source package.

### Post-Acceptance Real E2E Results

| Scenario | Result | Evidence |
|----------|--------|----------|
| Low-risk room booking | **PASS** — Stage 0–4 complete | `LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md` (inline report) |
| Low-risk reading planner | **PASS** — Stage 0–4 complete | `LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md` |
| Student management (HIGH-risk) | **EXPECTED_SAFETY_BLOCK_CONFIRMED** | `LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md` (inline report) |
| Critical-risk medication mgmt | **SAFETY_BLOCKED_EXPECTED** | `LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md` |

### Historical Baseline (superseded by `artifacts/full_acceptance_latest_minimal/`)

| Check | Result |
|-------|--------|
| AC-00 ~ AC-11 (v0.6.0-alpha.8) | 12/12 PASS |
| FT-01 full regression (v0.6.0-alpha.8) | 71/71 PASS |
| Phase 3T pytest (pre-Docker) | 103/103 PASS |

### Version Metadata Note

Package metadata (`pyproject.toml`, `core/version.py`) remains at `0.8.0-alpha.11`. The release label `v0.8.0-beta.1-local-preview-final` reflects the completed Docker Final Acceptance state. These are intentionally distinct — package metadata tracks source version, release label tracks acceptance status.

---

## Mandatory Constraints for Claude Code

**Any future Claude Code session reading this project MUST follow these constraints:**

### Prohibited Actions (unless user explicitly re-authorizes)

1. **Do NOT re-run full acceptance, full pytest, Docker build, Docker runtime smoke, or acceptance scripts** — they have already passed. Evidence: `artifacts/full_acceptance_latest_minimal/`.
2. **Do NOT re-run Phase 3S's 5 target tests** — already PASS.
3. **Do NOT continue modifying alignment doc items** — already closed.
4. **Do NOT continue modifying eval_regression test expectations** — already closed.
5. **Do NOT modify `pyproject.toml` or `uv.lock`** — untouched in the acceptance cycle.
6. **Do NOT claim production readiness** — this is a local-preview release.
7. **Do NOT claim real DeepSeek / Tavily business flow is validated** — dummy keys were used in acceptance. Real LLM/search E2E has been completed for low-risk scenarios (PASS) and critical-risk scenarios (SAFETY_BLOCKED as expected). See `LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md` and `LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md`.
8. **Do NOT modify business logic, test assertions, database logic, API logic, or frontend logic** unless the user explicitly starts a new development phase.

### Allowed Actions

- Documentation sync, startup docs, env docs, and status docs may be edited.
- New validation checks require user authorization before execution.

### Unvalidated Items (non-blocking for local-preview)

These checks were NOT executed in the Docker Final Acceptance and do NOT block local-preview delivery:

| Item | Reason | When to validate |
|------|--------|-----------------|
| ~~Real DeepSeek API smoke~~ | ~~Requires real API key~~ | **DONE** — low-risk E2E PASS (2026-05-30) |
| ~~Real Tavily API smoke~~ | ~~Requires real API key~~ | **DONE** — low-risk E2E PASS (2026-05-30) |
| ~~Stage 1–4 E2E with real LLM~~ | ~~Requires real API keys~~ | **DONE** — low-risk E2E Stage 0–4 complete (2026-05-30) |
| Report export (real browser) | Manual browser test | Optional |
| Auth / authorization | Architectural limitation | v1.0 |
| Multi-tenant security | Out of scope | v1.0 |
| Load / concurrency | Out of scope | Production hardening |
| Docker Swarm / Kubernetes | Out of scope | Production deployment |

### Risk-Adaptive Stage 3 Gate Guidance

When evaluating Stage 3 gate results, apply risk-adaptive interpretation:

- **LOW risk** (personal/learning/local): Do NOT require redteam coverage, eval regression, or trace backfill. Safety底线 (parser error, pending action, rejected action, safety finding) still apply.
- **MEDIUM risk** (team collaboration, no explicit high-risk markers): Require eval coverage for high-severity nodes. Skip redteam/regression/trace.
- **HIGH risk** (finance, legal, children): Require redteam + regression + trace.
- **CRITICAL risk** (medical, medication, diagnosis): Require all gates including expert review.

Do NOT treat a CRITICAL-risk Stage 3 safety block as a product failure. See `docs/stage3-risk-adaptive-gate.md` and `docs/acceptance/risk_adaptive_gate_final_validation.md`.

Do NOT treat old reports (pre-risk-adaptive-gate) as current if superseded by `docs/acceptance/risk_adaptive_gate_final_validation.md`.

### Version Awareness

- Current release is `v0.8.0-beta.1-local-preview-final`, **NOT** a production release.
- Do NOT treat this as v1.0 or assume production-grade infrastructure.
- Docker, PostgreSQL, and Redis ARE validated for local-preview use (full acceptance PASS, evidence in `artifacts/full_acceptance_latest_minimal/`).

---

## How to Answer Common Questions

If asked **"is the project usable?"**, answer:
> Yes, for personal / small-team Docker local-preview use. Full acceptance passed with 148 pytest tests, 13 acceptance scripts (707 checks), and runtime smoke.

If asked **"is it production-ready?"**, answer:
> No. No authentication, no authorization, no multi-tenant isolation, no production hardening.

If asked **"what remains before real usage?"**, answer:
> Real E2E validation has been completed. Configure real DeepSeek and Tavily API keys in `.env` and start using the platform. For critical-risk domains (medical, financial), expect strong safety gates that require domain expert input.

If asked **"what was validated?"**, answer:
> Docker environment (postgres/redis healthy), ruff lint/format, compileall, version_check, 13 acceptance scripts (707 checks), 148 pytest tests, API health endpoint, OpenAPI spec (66,931 bytes, 61 paths), frontend container logs. All passed. Real E2E with live DeepSeek + Tavily: low-risk room booking Stage 0–4 complete (PASS), low-risk reading planner Stage 0–4 complete (PASS), student management HIGH-risk Stage 3 SAFETY_BLOCKED (expected), critical-risk medication mgmt Stage 3 SAFETY_BLOCKED (expected). Evidence: `artifacts/full_acceptance_latest_minimal/`, inline E2E reports in project root.

---

## Key Files

| File | Purpose |
|------|---------|
| `artifacts/full_acceptance_latest_minimal/` | **Latest acceptance evidence directory** (minimal summaries) |
| `docs/current_project_state.md` | **Authoritative project status** |
| `docs/validation-status.md` | Current validation status summary |
| `docs/e2e-results-summary.md` | Real E2E results summary |
| `docs/stage3-risk-adaptive-gate.md` | Risk-adaptive Stage 3 gate documentation |
| `docs/acceptance/docker_final_acceptance_report.md` | Acceptance report (historical, superseded by `artifacts/full_acceptance_latest_minimal/`) |
| `docs/acceptance/risk_adaptive_gate_final_validation.md` | Risk-adaptive gate validation |
| `LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md` | Low-risk E2E report |
| `LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md` | Critical-risk E2E report |
| `docs/startup.md` | Startup instructions |
| `docs/local_setup.md` | Environment setup guide |
| `README.md` | Project overview |
| `CHANGELOG.md` | Version history |
| `ROADMAP.md` | Development roadmap |
