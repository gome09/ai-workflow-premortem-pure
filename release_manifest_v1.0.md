# v1.0 Release Manifest

## Included Production Paths

### Core Application

| Path | Purpose |
|---|---|
| `api/` | FastAPI application — entry point `api/main.py` |
| `api/routers/` | API route handlers (chat, session, stage, oversight, evidence, safety, eval, redteam, reports, traces, interrupts) |
| `auth/` | JWT authentication, password hashing, RBAC permissions |
| `core/` | Business logic services, models, config, execution modes |
| `core/gates/` | Stage advancement gate engine and pluggable rule system |
| `core/gates/rules/` | Built-in gate rules (eval regression, redteam coverage, stage3 eval failure, trace backfill) |
| `core/llm/` | LLM provider abstraction, structured output parsing, retry logic |
| `core/llm/adapters/` | DeepSeek and mock LLM adapters (openai_compatible is a stub) |
| `core/migrations/` | Context JSON backward-compat migrations (retained — active at read time) |
| `graph/` | Execution graph package |
| `graph/runner.py` | Production execution path — `run_one_step()` |
| `graph/nodes.py` | Stage node dispatchers |
| `graph/langgraph_interrupt_runner.py` | Experimental interrupt execution path (non-default) |
| `graph/interrupts.py` | Interrupt record mapping helpers |
| `graph/transition_policy.py` | Action-to-interrupt policy evaluation |
| `graph/interrupt_gate.py` | Interrupt gate protocol |
| `graph/review_gate.py` | Review gate protocol |
| `storage/` | Storage backend abstraction |
| `storage/backends/postgres.py` | PostgreSQL backend |
| `storage/backends/sqlite_store.py` | SQLite backend (dev/lite) |
| `stages/` | Stage executor implementations (Stage 1–4) and domain profiles |
| `tools/` | Evidence filters, rankers, risk taxonomy, safety classifier, search |
| `tools/taxonomies/` | Deterministic risk/failure taxonomy mappings (NIST, OWASP, Microsoft, domain-specific) |
| `alembic/` | Database schema migrations |
| `alembic/versions/` | V001–V003 schema migrations |
| `scenarios/` | Scenario manifests and registry |
| `frontend/` | Streamlit UI (`frontend/app.py`) |
| `monitoring/` | Prometheus/Grafana monitoring configs |
| `nginx/` | Nginx reverse proxy config |
| `docs/` | User-facing documentation |
| `pyproject.toml` | Project metadata and dependencies |
| `Dockerfile` | Production container image |
| `docker-compose.yml` | Full-stack compose |
| `docker-compose.lite.yml` | Lite (SQLite) compose |
| `alembic.ini` | Alembic config |

### Key Scripts (Active)

| Script | Purpose |
|---|---|
| `scripts/version_check.py` | Validates pyproject.toml ↔ core/version.py alignment |
| `scripts/gen_certs.sh` / `gen_certs.ps1` | TLS cert generation for local HTTPS |
| `scripts/gen_secrets.sh` | .env secret generation |

## Excluded / Archived Paths

| Path | Reason |
|---|---|
| `scripts/archive/` | One-time and manual scripts not part of production workflow |
| `scripts/archive/migrate_add_tenant_once.py` | One-time tenant backfill (run once post Phase-A deployment) |
| `scripts/archive/live_e2e_low_risk_room_booking.py` | Manual live E2E — not in CI |
| `scripts/archive/live_e2e_student_management_v2.py` | Manual live E2E — not in CI |
| `scripts/archive/stage_advancement_source_freeze_audit_alpha11.py` | Alpha.11 assumptions, stale for v1.0 |
| `graph/builder.py` | Deleted — experimental full-graph LangGraph builder, no tests |
| `graph/edges.py` | Deleted — only used by graph/builder.py |
| `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/` | Tool caches — excluded by .dockerignore |
| `data/` | SQLite dev data files — excluded by .dockerignore |
| `artifacts/` | Live E2E test artifacts — excluded by .dockerignore |

## Experimental (Present, Non-Default)

| Path | Status |
|---|---|
| `graph/langgraph_interrupt_runner.py` | Experimental — active only when `WORKFLOW_EXECUTION_MODE=langgraph_interrupt` |
| `graph/interrupts.py` | Experimental support for interrupt adapter |
| `core/execution_mode.py` → `LANGGRAPH_INTERRUPT` | Config value exists; no dedicated test coverage |
| `core/llm/adapters/openai_compatible.py` | Stub — raises `NotImplementedError` |

## Validation Summary

| Command | Result |
|---|---|
| `python -m compileall .` | ✅ Exit 0 |
| `python scripts/version_check.py` | ✅ `Version metadata OK: 1.0.0` |
| `pytest --collect-only` | ✅ 389 tests collected |
| `pytest` | ✅ **384 passed, 5 skipped** |
| `ruff check .` | ⚠️ 7 pre-existing errors (I001 × 6, UP037 × 1) — not introduced by this cleanup |
| `mypy . --exclude frontend` | ⚠️ 80 pre-existing errors — not introduced by this cleanup |

## Remaining Decisions

| Decision | Owner |
|---|---|
| Should `LANGGRAPH_INTERRUPT` mode be formally supported or removed in a future release? Requires test coverage and docs if kept. | Business/Engineering |
| Should `core/llm/adapters/openai_compatible.py` stub be completed or removed? | Engineering |
| When can `core/migrations/` be removed? Safe when all persisted contexts have `context_schema_version >= "0.7.0"`. | Operations/Data |
| Resolve 7 pre-existing ruff errors (`I001` import sort, `UP037` annotation) in a follow-up linting pass. | Engineering |
| Resolve 80 pre-existing mypy errors in a follow-up type-annotation pass. | Engineering |
| `scripts/archive/migrate_add_tenant_once.py` — confirm it has been run on all production instances before deleting. | Operations |
