# v1.0 Release Cleanup Notes

## Current Production Path

| Item | Value |
|---|---|
| API entry | `uvicorn api.main:app` → `api/main.py` |
| Execution mode (default) | `SINGLE_STEP` via `graph/runner.py` → `run_one_step()` |
| Storage backend | PostgreSQL (`storage/backends/postgres.py`) or SQLite (`storage/backends/sqlite_store.py`) |
| Database migration mechanism | Alembic (`alembic/versions/`) |
| Context schema migration | `core/migrations/migrate_context()` — auto-runs at context load time |
| Version source | `core/version.py` → `APP_VERSION = "1.0.0"` (validated by `scripts/version_check.py`) |

## Removed or Archived Legacy Components (Second Round)

| Component | Action | Reason |
|---|---|---|
| `graph/builder.py` | Deleted | Experimental full-graph LangGraph builder; no tests, no production callers, explicitly marked non-production |
| `graph/edges.py` | Deleted | Only used by `graph/builder.py`; no independent production use |
| `scripts/migrate_add_tenant.py` | Archived → `scripts/archive/migrate_add_tenant_once.py` | One-time tenant backfill script; not invoked by CI or Makefile |
| `scripts/live_e2e_low_risk_room_booking.py` | Archived → `scripts/archive/` | Manual live E2E script; not in CI |
| `scripts/live_e2e_student_management_v2.py` | Archived → `scripts/archive/` | Manual live E2E script; not in CI |

### First-Round Archive (from round 1, retained here for completeness)

| Component | Action | Reason |
|---|---|---|
| `scripts/archive/stage_advancement_source_freeze_audit_alpha11.py` | Archived | Alpha.11 assumptions stale for v1.0 |
| `storage/migrations/` legacy registry | Deleted (round 1) | Confirmed no references |

## Experimental Components

| Component | Status | Notes |
|---|---|---|
| `graph/langgraph_interrupt_runner.py` | Experimental — not default | Activated only when `workflow_execution_mode=langgraph_interrupt`. No dedicated test suite. Production default is `SINGLE_STEP`. |
| `graph/interrupts.py` | Experimental support | Interrupt record mapping helpers; only meaningful in `langgraph_interrupt` mode |
| `core/execution_mode.py` → `LANGGRAPH_INTERRUPT` | Experimental config value | Config value exists; code path is wired but has no test coverage and is not documented in README as supported |
| `core/llm/adapters/openai_compatible.py` | Stub — not implemented | Raises `NotImplementedError`; live integration deferred |

## Active Legacy Components (Retained by Design)

| Component | Reason retained |
|---|---|
| `core/migrations/` | Actively called by `storage/backends/postgres.py` and `sqlite_store.py` on every context load; required for backward compat with pre-v0.7.0 persisted context JSON. See `core/migrations/README.md`. |

## Alpha / v0.x Docstring Cleanup

The following production source files had alpha/v0.x version labels in docstrings or inline comments that described current (not historical) behavior. These were updated to remove the misleading version labels while preserving the behavioral description:

- `core/models.py` — 12 docstrings / inline comments
- `core/gates/base.py`, `core/gates/report.py`, `core/gates/models.py`
- `core/gates/rules/eval_regression.py`, `redteam_coverage.py`, `stage3_eval_failure.py`, `trace_backfill_gap.py`
- `core/eval_judge.py`
- `core/llm/structured_output.py`, `core/llm/adapters/openai_compatible.py`
- `core/stage_advancement_contract.py`, `core/stage_advancement_coordinator.py`
- `core/stage_advancement_decision.py`, `core/stage_resolution_service.py`
- `core/stage_revision_service.py`, `core/stage_scope_service.py`, `core/stage_operation_service.py`
- `core/oversight_service.py`, `core/reviewed_output_service.py`, `core/redteam_service.py`
- `core/session_service.py` — section header comments
- `api/routers/interrupts.py`, `api/routers/oversight.py`
- `graph/interrupts.py`, `tools/taxonomies/__init__.py`

**Not changed (historical data, not misleading docstrings):**
- `core/migrations/` — version constants (`CURRENT_CONTEXT_SCHEMA_VERSION = "0.7.0"`) and migration function names are data identifiers
- `core/models.py` — `CONTEXT_SCHEMA_VERSION`, `ACTION_SCHEMA_VERSION`, `prompt_template_version` field defaults
- `core/redteam_service.py:415` — `tags=["redteam", "stage3", "v0.8-alpha.3"]` is a runtime data tag
- `core/trace_backfill_service.py:185` — `"v0.8-alpha.8"` is a runtime data tag
- `core/eval_*_service.py` — `gate_effect` dict values are runtime identifiers
- Test files — historical fixture versions preserved

## Known Non-Blocking Issues

| Issue | Reason not blocking release |
|---|---|
| `graph/langgraph_interrupt_runner.py` has no dedicated test suite | Mode is not default; production path (SINGLE_STEP) has 384+ passing tests |
| `core/stage_readiness_service.py` still references v0.6/v0.7 in one inline comment | Describes backward-compat logic, not current behavior claim |
| `core/eval_regression_policy.py` has one inline threshold comment referencing alpha.2 | Describes threshold origin, not current behavior; low risk of confusion |
| mypy errors (pre-existing) | Not introduced by this cleanup; see validation section |
| `core/llm/adapters/openai_compatible.py` raises NotImplementedError | Placeholder is explicit and documented; not reachable from default execution path |
| Git identity not configured in environment | `git commit` succeeded (user has global git config); identity confirmed working |

## Validation Commands

| Command | Result |
|---|---|
| `python -m compileall .` | ✅ Exit 0 — no syntax errors |
| `python scripts/version_check.py` | ✅ `Version metadata OK: 1.0.0` |
| `pytest --collect-only` | ✅ 389 tests collected |
| `pytest` | ✅ 384 passed, 5 skipped |
| `ruff check .` | ⚠️ 7 pre-existing errors (6×I001 import sort, 1×UP037 annotation) — none in files modified this round |
| `mypy . --exclude frontend` | ⚠️ 80 pre-existing errors — none introduced by this cleanup round |
