# Docker Final Local-Preview Acceptance Ledger

> **⚠️ SUPERSEDED** — This ledger has been superseded by the latest full acceptance.
> See `artifacts/full_acceptance_latest_minimal/` for the current authoritative acceptance evidence.
> This file is retained for historical traceability only.

> **Date:** 2026-05-30
> **Target:** personal / small-team local-preview (NOT production)
> **Env:** dummy `.env.acceptance` (no real DeepSeek / Tavily keys)

---

## Phase 1: Docker Environment Cleanup & Build

| Item | Command | Status | Code Changed | Files Changed | Rerun? | Rerun Reason | Output Summary |
|------|---------|--------|-------------|---------------|--------|-------------|----------------|
| docker_compose_down | `docker compose down -v --remove-orphans` | PASS | No | — | No | — | All containers, volumes, networks removed |
| docker_compose_build | `docker compose build --no-cache api frontend` | PASS | No | — | No | — | api + frontend images built successfully |

## Phase 2: Start Dependency Services

| Item | Command | Status | Code Changed | Files Changed | Rerun? | Rerun Reason | Output Summary |
|------|---------|--------|-------------|---------------|--------|-------------|----------------|
| start_postgres_redis | `docker compose up -d postgres redis` | PASS | No | — | No | — | postgres + redis containers created and started |
| verify_services | `docker compose ps` | PASS | No | — | No | — | postgres (healthy), redis (healthy) |

## Phase 3: Docker Static Quality Checks

| Item | Command | Status | Code Changed | Files Changed | Rerun? | Rerun Reason | Output Summary |
|------|---------|--------|-------------|---------------|--------|-------------|----------------|
| ruff_check | `docker compose run --rm api uv run ruff check .` | FIXED | Yes | graph/nodes.py + 30 auto-fixed files | Yes | Initial run had 31 errors (I001 import sorting, F401 unused imports, F841 unused var). Fixed via ruff --fix + manual removal of unused `next_running_states`. Re-run: PASS | All checks passed! |
| ruff_format | `docker compose run --rm api uv run ruff format --check .` | FIXED | Yes | 38 files reformatted | Yes | Initial run had 38 files needing reformat. Ran `ruff format .`. Re-run: PASS | 215 files already formatted |
| compileall | `docker compose run --rm api python -m compileall -q api core graph stages tools storage frontend scripts` | PASS | No | — | No | — | No compilation errors |
| version_check | `docker compose run --rm api uv run python scripts/version_check.py` | PASS | No | — | No | — | Version metadata OK: 0.8.0-alpha.11 |

## Phase 4: Docker Acceptance Scripts

| Item | Command | Status | Code Changed | Files Changed | Rerun? | Rerun Reason | Output Summary |
|------|---------|--------|-------------|---------------|--------|-------------|----------------|
| ac09a | `docker compose run --rm api //opt/aiwf-venv/bin/python scripts/acceptance/_run_helper.py scripts/acceptance/ac09a_report_artifact_export.py` | FIXED | Yes | scripts/acceptance/ac09a_report_artifact_export.py + scripts/acceptance/_run_helper.py (new) | Yes | Initial: import error (PYTHONPATH not set) + criterion 6 false positive. Fixed: created helper for PYTHONPATH, fixed criterion 6 AST-based check. Re-run: PASS | 70/70 checks passed |
| ac09b_fix | `docker compose run --rm api //opt/aiwf-venv/bin/python scripts/acceptance/_run_helper.py scripts/acceptance/ac09b_fix_reports_router_testclient.py` | PASS | No | — | No | — | 53/53 checks passed |
| ac09b_persist | `docker compose run --rm api //opt/aiwf-venv/bin/python scripts/acceptance/_run_helper.py scripts/acceptance/ac09b_report_api_persistence.py` | PASS | No | — | No | — | 61/61 checks passed |
| ac09c | `docker compose run --rm api //opt/aiwf-venv/bin/python scripts/acceptance/_run_helper.py scripts/acceptance/ac09c_pg_report_artifacts_persistence.py` | FIXED | Yes | storage/session_store.py | Yes | evidence_sources INSERT had 16 VALUES placeholders but only 14 columns/params. Fixed to 14. Re-run: PASS | 58/58 checks passed |
| ac10a | `.../ac10a_streamlit_report_panel_minimum.py` | PASS | No | — | No | — | 48/48 checks passed |
| ac10b | `.../ac10b_streamlit_stage_gate_actions_minimum.py` | PASS | No | — | No | — | 57/57 checks passed |
| ac10c | `.../ac10c_streamlit_evidence_panel_minimum.py` | PASS | No | — | No | — | 49/49 checks passed |
| ac10d | `.../ac10d_streamlit_safety_eval_panels_minimum.py` | PASS | No | — | No | — | 78/78 checks passed |
| ac10e | `.../ac10e_streamlit_audit_workbench_closure.py` | PASS | No | — | No | — | 67/67 checks passed |
| ac11a | `.../ac11a_interrupt_adapter_boundary.py` | FIXED | Yes | scripts/acceptance/ac11a_interrupt_adapter_boundary.py | Yes | Check expected literal `evaluate_stage_gate` in nodes.py but stage gate is called via `advance_stage_if_ready`. Fixed check to accept both. Re-run: PASS | 74/74 checks passed |

## Phase 5: Docker Full Pytest Regression

| Item | Command | Status | Code Changed | Files Changed | Rerun? | Rerun Reason | Output Summary |
|------|---------|--------|-------------|---------------|--------|-------------|----------------|
| full_pytest | `docker compose run --rm api uv run pytest tests/ -x -q` | PASS | No | — | No | — | 103 passed in 5.73s, 0 failed |

## Phase 6: Docker Runtime Smoke

| Item | Command | Status | Code Changed | Files Changed | Rerun? | Rerun Reason | Output Summary |
|------|---------|--------|-------------|---------------|--------|-------------|----------------|
| start_services | `docker compose up -d api frontend` | PASS | No | — | No | — | api + frontend containers started |
| health_check | `curl -f http://localhost:8000/health` | PASS | No | — | No | — | {"status":"ok","version":"0.8.0-alpha.11",...} |
| openapi_check | `curl -f http://localhost:8000/openapi.json` | PASS | No | — | No | — | OpenAPI 3.1.0 spec returned successfully |
| api_logs | `docker compose logs --tail=200 api` | PASS | No | — | No | — | No Traceback/ImportError/fatal errors. App started cleanly |
| frontend_logs | `docker compose logs --tail=200 frontend` | PASS | No | — | No | — | No Traceback/ImportError/fatal errors. Streamlit running on :8501 |

## Phase 7: Final Report

| Item | Status |
|------|--------|
| final_report | PASS |

---

## Summary

- **Total items:** 22
- **PASS:** 17
- **FIXED:** 5
- **FAIL:** 0
- **BLOCKED:** 0
- **NOT_RUN:** 0
