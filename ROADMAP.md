# Roadmap

> **Last updated:** 2026-05-31 (final delivery alignment update)

---

## Current Status

**Release:** `v0.8.0-beta.1-local-preview-final`
**Acceptance:** Docker Final Local-Preview Acceptance — PASS

---

## Completed

- [x] Core workflow engine (Stage 1–4, single_step execution)
- [x] Human oversight gates (PendingHumanAction, Review Gate, Stage Gate)
- [x] Evidence / Safety / Eval governance
- [x] Stage advancement contracts
- [x] Report artifact generation (JSON / Markdown)
- [x] Streamlit Review Workbench
- [x] PostgreSQL + Redis integration
- [x] Docker Compose local deployment
- [x] v0.6.0-alpha.8 acceptance (AC-00 ~ AC-11, FT-01: 71/71 PASS)
- [x] v0.8.0-alpha.1–alpha.11 feature development (Eval, Red Team, Trace Backfill, etc.)
- [x] Phase 3T pytest regression (103/103 PASS) — historical; latest: 148/148 PASS
- [x] Docker Final Local-Preview Acceptance (all phases PASS)
- [x] Personal / small-team local-preview readiness
- [x] Real E2E with live DeepSeek + Tavily (low-risk PASS, critical-risk SAFETY_BLOCKED)
- [x] EvidenceSource unhashable bug fix (3 regression tests)
- [x] Report export IndexError fix (7 robustness tests)
- [x] Risk-adaptive Stage 3 gate (26 tests, 3 smokes)

## Next Steps (Optional)

### Before First Real Use

- [x] Get real DeepSeek API key from [platform.deepseek.com](https://platform.deepseek.com)
- [x] Get real Tavily API key from [tavily.com](https://tavily.com)
- [x] Configure `.env` with real keys
- [x] Run live smoke: create session → run Stage 1 → verify DeepSeek responds → verify Tavily results appear
- [x] Real E2E validation: low-risk Stage 0–4 complete (PASS), critical-risk SAFETY_BLOCKED (expected)
- [x] Risk-adaptive Stage 3 gate: implemented and validated (26/26 tests, 3 smokes)
- [x] Ready for real personal/small-team use

### Future Development (if explicitly scoped)

- [ ] v0.9.0-pre-alpha: governance scaffolding (low-coupling only)
- [ ] ruff / lint formal integration
- [ ] compileall formal integration
- [ ] version_check formal integration
- [ ] Stage 1–4 E2E with real LLM
- [ ] Report export runtime validation

### Production Hardening (v1.0 — NOT currently planned)

- [ ] Authentication / Authorization / RBAC
- [ ] Multi-tenant isolation
- [ ] Rate limiting
- [ ] Secrets management hardening
- [ ] Production observability / monitoring
- [ ] Load / concurrency testing
- [ ] Docker Swarm / Kubernetes deployment
- [ ] Public internet security hardening

---

## Explicitly Out of Scope

- Production deployment (Docker Swarm, Kubernetes) — not claimed
- Public internet deployment — not supported
- Multi-tenant enterprise use — not supported
- Unsupervised automated decisions — not supported

---

## Historical Roadmaps

The following roadmap documents are retained for historical context. They do NOT represent the current project status.

- `docs/v09_pre_alpha_entry_criteria.md` — v0.9 entry criteria (historical planning)
- `docs/v0.8.0-alpha.1-eval-dataset-experiment-foundation.md` — alpha.1 design
- `docs/v0.8.0-alpha.2-regression-gate-integration.md` — alpha.2 design
- `docs/v0.8.0-alpha.3-redteam-foundation.md` — alpha.3 design
- `docs/v0.8.0-alpha.4-taxonomy-mapping.md` — alpha.4 design
- `docs/v0.8.0-alpha.5-eval-judgment-calibration.md` — alpha.5 design
- `docs/v0.8.0-alpha.6-trace-backfill-report-closure.md` — alpha.6 design
- `docs/v0.8.0-alpha.8-stage-advancement-prevalidation.md` — alpha.8 design
- `docs/v0.8.0-alpha.9-stage-advancement-hardening.md` — alpha.9 design

For the current authoritative project status, see [docs/current_project_state.md](docs/current_project_state.md).
