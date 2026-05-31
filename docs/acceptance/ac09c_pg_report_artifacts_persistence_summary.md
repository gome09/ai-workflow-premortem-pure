# AC-09C Real PostgreSQL report_artifacts Persistence — Acceptance Summary

**Date:** 2026-05-09
**Result:** ALL PASS (58/58 checks, 100%)
**Schema version:** 0.6.0-alpha.8
**Database:** `postgresql://postgres@localhost:5432/ai_workflow` (development)

---

## 1. Current Implementation Observations

### report_artifacts DDL ([storage/session_store.py:146-159](../../storage/session_store.py#L146-L159))
```sql
CREATE TABLE IF NOT EXISTS report_artifacts (
    report_id         TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    version           TEXT NOT NULL,
    content_json      JSONB NOT NULL DEFAULT '{}',
    content_markdown  TEXT NOT NULL DEFAULT '',
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE report_artifacts ADD COLUMN IF NOT EXISTS content_markdown TEXT NOT NULL DEFAULT '';
```

### content_json / content_markdown column definitions
| Column | Type | Default |
|--------|------|---------|
| report_id | text | (PK) |
| session_id | text | NOT NULL, FK→sessions |
| version | text | NOT NULL |
| content_json | jsonb | `'{}'` |
| content_markdown | text | `''` |
| generated_at | timestamptz | `NOW()` |

### Save / upsert (`_sync_report_artifacts`, lines 455-476)
`INSERT ... ON CONFLICT (report_id) DO UPDATE SET version, content_json, content_markdown`

### List / get (lines 639-697)
Both `list_report_artifacts()` and `get_report_artifact()` query the `report_artifacts` table and return dicts including `content_json`, `content_markdown`, `eval_runs`, `failed_eval_runs`, and governance field mirrors.

### SessionStore initialization (`initialize()`, lines 265-270)
Executes `CREATE_TABLES_SQL` (includes all `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN IF NOT EXISTS` statements) in a single transaction.

---

## 2. Modification Summary

**无生产代码修改** — No production code changes were needed.

All four production files passed as-is against real PostgreSQL:
- `storage/session_store.py` — no changes (DDL, save, list, get all correct)
- `core/models.py` — no changes
- `core/report_service.py` — no changes
- `core/session_service.py` — no changes

Only new file: [scripts/acceptance/ac09c_pg_report_artifacts_persistence.py](../../scripts/acceptance/ac09c_pg_report_artifacts_persistence.py)

---

## 3. Key Code Changes

None required. The DDL, upsert, list, and get implementations from AC-09B already handled `content_markdown` correctly against real PostgreSQL.

---

## 4. Commands Executed

| Command | Result |
|---------|--------|
| `python -m py_compile storage/session_store.py` | OK |
| `python -m py_compile core/models.py` | OK |
| `python -m py_compile core/report_service.py` | OK |
| `python -m py_compile core/session_service.py` | OK |
| `python -m py_compile scripts/acceptance/ac09c_pg_report_artifacts_persistence.py` | OK |
| `python scripts/acceptance/ac09c_pg_report_artifacts_persistence.py` | 58/58 PASS |

**Verified:** non-production database (`app_env=development`, `localhost:5432`, `ai_workflow`).

**NOT executed:** pytest, uvicorn, Streamlit, Docker, Redis, LLM, Tavily.

---

## 5. Test / Verification Results

### PostgreSQL connection (1/1 PASS)
- Connected to `localhost:5432/ai_workflow` (development) successfully
- Production safeguards confirmed: `app_env=development`, no AWS RDS / Cloud SQL markers

### Table existence & columns (8/8 PASS)
- `report_artifacts` table exists
- All 6 columns present: report_id (text), session_id (text), version (text), content_json (jsonb), content_markdown (text), generated_at (timestamptz)

### DDL idempotency (2/2 PASS)
- `initialize()` ran twice without errors — DDL is fully idempotent

### Synthetic context (4/4 PASS)
- ReportArtifact created with report_id=RPT-xxx, 39 content_json keys, 9029 chars markdown
- context.report_artifacts count = 1

### SessionStore.save (1/1 PASS)
- `store.save(ctx)` wrote to real PostgreSQL without errors

### SessionStore.list (10/10 PASS)
- 1 artifact returned; report_id, version, generated_at, content_json, content_markdown all present
- All 8 governance keys in content_json: all_actions, audit_events, evidence_sources, safety_findings, eval_summary, eval_runs, stage_readiness, open_risks

### SessionStore.get by id (10/10 PASS)
- report_id matches, content_json + content_markdown present and substantial
- All 8 governance keys verified in read-back content_json

### Direct SQL verification (10/10 PASS)
- `SELECT content_json, content_markdown FROM report_artifacts WHERE report_id = ...` confirmed both non-empty
- content_markdown: 9029 chars stored in DB
- All 8 governance keys verified in DB content_json

### Upsert test (3/3 PASS)
- Same report_id saved twice → exactly 1 row (no duplicate)
- content_markdown updated with marker appended (9029→9066 chars)
- Marker found in DB read-back

### Cleanup (1/1 PASS)
- Test session deleted via `DELETE FROM sessions WHERE session_id = ...` (CASCADE removes child rows)
- Only AC-09C test data affected

### Scope isolation (1/1 PASS)
- No production logic modified

### py_compile (5/5 PASS)
- All 5 files compile cleanly

---

## 6. Acceptance Criteria Checklist

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Non-production PostgreSQL; result is PASS not BLOCKED | **PASS** |
| 2 | `report_artifacts` table exists, `content_markdown` column exists | **PASS** |
| 3 | DDL initialization is idempotent (repeated `initialize()` / `ALTER TABLE` no error) | **PASS** |
| 4 | SessionStore.save writes content_json + content_markdown | **PASS** |
| 5 | SessionStore.list reads back artifact metadata + content fields | **PASS** |
| 6 | SessionStore.get reads back full artifact by report_id | **PASS** |
| 7 | Direct SQL confirms content_json + content_markdown non-empty with governance keys | **PASS** |
| 8 | Upsert: same report_id saved twice → 1 row, markdown updated | **PASS** |
| 9 | Only AC-09C test data cleaned; no other sessions affected | **PASS** |
| 10 | No modification to single_step, gates, action/audit/eval/safety logic | **PASS** |
| 11 | No pytest, no service startup, no Redis/LLM/Tavily | **PASS** |

---

## 7. Unresolved Risks (deferred)

1. **Redis round-trip**: `ContextCache.set()`/`.get()` with `model_dump_json()` not tested against Redis.
2. **Real four-stage session report**: Synthetic context only; reports from LLM-executed workflows not tested.
3. **Streamlit report panel**: Frontend integration with persisted reports not validated.
4. **Full API integration**: FastAPI + session_service + session_store integration not tested end-to-end.
5. **Concurrent writes**: No concurrency/locking tests performed.

---

## 8. Recommended Next Step

AC-09C PASSES. Real PostgreSQL persistence is confirmed. Recommended: **AC-10A — Streamlit Review Workbench report panel minimum acceptance** to verify the frontend report panel reads and displays persisted report artifacts.
