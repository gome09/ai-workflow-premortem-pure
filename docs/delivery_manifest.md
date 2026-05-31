# Delivery Manifest — v0.8.0-beta.1-local-preview-final

**Source version:** `0.8.0-alpha.11`
**Release / acceptance label:** `v0.8.0-beta.1-local-preview-final`
**Generated:** 2026-05-31 (final delivery alignment update)
**Runtime validation:** `docker_final_local_preview_pass`
**Real E2E validation:** `low_risk_room_booking_pass__low_risk_reading_planner_pass__student_management_safety_block_confirmed__critical_risk_safety_blocked_expected`

---

## 1. Purpose

This manifest supersedes the earlier `v0.8.0-alpha.11 Freeze Fix` delivery manifest.

The package is now aligned as a **local-preview final** delivery: source metadata remains `0.8.0-alpha.11`, while the acceptance/release label is `v0.8.0-beta.1-local-preview-final`.

---

## 2. Version and Status Contract

| Item | Value |
|------|-------|
| `pyproject.toml` version | `0.8.0-alpha.11` |
| `core/version.py` `APP_VERSION` | `0.8.0-alpha.11` |
| Public release / acceptance label | `v0.8.0-beta.1-local-preview-final` |
| Acceptance scope | Personal and small-team local preview |
| Production status | **NOT production-ready** |

The source version and release label are intentionally distinct. The source version identifies the code package; the release label identifies the completed local-preview acceptance state.

---

## 3. Validation Evidence

| Validation Area | Result |
|-----------------|--------|
| Docker environment | postgres healthy, redis healthy |
| ruff check / format | PASS |
| compileall / version_check | PASS (0.8.0-alpha.11) |
| Acceptance scripts | PASS — 13 scripts, 707 checks |
| Full pytest | PASS — 148/148 |
| API /health | ok |
| OpenAPI | 66,931 bytes, 61 paths |
| Frontend container | running, logs clean |
| Runtime logs | no Traceback / ImportError / ValidationError / RuntimeError |
| Real DeepSeek + Tavily low-risk room booking E2E | PASS — Stage 0–4 complete, report creation 200 |
| Real DeepSeek + Tavily low-risk reading planner E2E | PASS — Stage 0–4 complete |
| Student management HIGH-risk E2E | EXPECTED_SAFETY_BLOCK_CONFIRMED — Stage 3 blocked |
| Critical-risk medical E2E | SAFETY_BLOCKED_EXPECTED — Stage 3 correctly blocked |
| Risk-adaptive Stage 3 gate | PASS — 26/26 tests, 3 smokes |
| Report export robustness | PASS — 7/7 tests |

**Evidence directories:**
- `artifacts/full_acceptance_latest_minimal/` — deterministic acceptance summaries
- Inline E2E reports in project root (`LIVE_E2E_*.md`) — real E2E results

---

## 4. Updated Current Documentation

The following files define the current delivery state:

1. `README.md`
2. `SECURITY.md`
3. `CHANGELOG.md`
4. `docs/current_project_state.md`
5. `docs/validation-status.md`
6. `docs/e2e-results-summary.md`
7. `docs/current-status-index.md`
8. `docs/acceptance/README.md`
9. `docs/acceptance/docker_final_acceptance_report.md`
10. `docs/acceptance/risk_adaptive_gate_final_validation.md`
11. `LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md`
12. `LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md`
13. `artifacts/full_acceptance_latest_minimal/`
14. `artifacts/final_package_verification/`

Historical alpha freeze-fix files are retained for traceability only and do not define the current delivery status.

---

## 5. Personal / Small-Team Usage Boundary

**Ready for:**

- Personal local use
- 2–5 person trusted small-team local use
- AI project pre-mortem analysis
- Failure mode identification
- Human oversight workflow design
- EvalCase draft generation
- Local JSON / Markdown report export

**Not ready for:**

- Public internet deployment
- Production SaaS
- Enterprise multi-tenant use
- Unsupervised automated decisions
- Regulated medical, legal, financial, or safety-critical deployment without independent governance
- Any deployment requiring authentication, authorization, RBAC, rate limiting, or production observability

---

## 6. Security Handling

Credential fragments have been redacted from live E2E reports. Do not commit real API keys, database passwords, runtime exports, or local `.env` files.

If a package containing credential fragments has already been shared, rotate the corresponding keys before further use.

---

## 7. Next Recommended Work

Before moving beyond personal/small-team local use:

1. Add authentication and authorization.
2. Restrict CORS and public ports.
3. Add secrets management.
4. Add rate limiting and abuse controls.
5. Add production observability.
6. Add load/concurrency testing.
7. Add deployment hardening for Docker/Kubernetes.
8. Define governance rules for regulated or high-impact domains.
