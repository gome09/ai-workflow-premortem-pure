# AC-09B ReportArtifact Persistence & Reports API — Acceptance Summary

**Date:** 2026-05-09
**Result:** ALL PASS (61/61 checks, 100%)
**Schema version:** 0.6.0-alpha.8

---

## 1. Current Implementation Observations

### Reports router (`api/routers/reports.py`)
| Route | Handler | Delegates to |
|-------|---------|-------------|
| `POST /sessions/{id}/reports` | `create_report_artifact` | `session_service.create_report_artifact()` |
| `GET /sessions/{id}/reports` | `list_report_artifacts` | `session_service.list_report_artifacts()` |
| `GET /sessions/{id}/reports/{report_id}` | `get_report_artifact` | `session_service.get_report_artifact()` |

### ReportArtifact model (`core/models.py:371-386`)
Fields: `report_id`, `session_id`, `version`, `generated_at`, `ai_generated`, `human_reviewed`, `evidence`, `audit_events`, `open_risks`, `eval_summary`, `eval_runs`, `failed_eval_runs`, `content_json`, `content_markdown`

### Create/list/get call chain
```
Router → SessionService → report_service.create_report_artifact() → ctx
                         → session_store.save(ctx)
                         → context_cache.set(ctx)
                         → return artifact.model_dump(mode="json")
```

### Session save/load path
- `SessionStore.save(ctx)` — upserts `sessions` table (context_json) + syncs individual tables including `report_artifacts`
- `SessionStore.load(session_id)` — `ProjectContext.model_validate(row["context_json"])`
- `SessionStore.list_report_artifacts(session_id)` — queries `report_artifacts` table
- `SessionStore.get_report_artifact(session_id, report_id)` — queries single row
- `ContextCache.set(ctx)` — Redis `model_dump_json()`
- `ContextCache.get(session_id)` — Redis → `model_validate_json()`

### report_artifacts DB mapping
`CREATE TABLE report_artifacts (report_id, session_id, version, content_json, content_markdown, generated_at)` with upsert sync in `_sync_report_artifacts()`.

---

## 2. Modification Summary

**Production code modified:** YES (4 files, minimal scope)

| File | Change | Purpose |
|------|--------|---------|
| [core/models.py:385-386](../../core/models.py#L385-L386) | Added `content_markdown: str = ""` to `ReportArtifact` | Store markdown report alongside JSON |
| [core/report_service.py:230](../../core/report_service.py#L230) | Added `content_markdown=content_md` to `create_report_artifact()` | Generate and persist markdown on artifact creation |
| [storage/session_store.py:148-152](../../storage/session_store.py#L148-L152) | Added `content_markdown TEXT` column + `ALTER TABLE` to `report_artifacts` DDL | DB schema for markdown persistence |
| [storage/session_store.py:453-472](../../storage/session_store.py#L453-L472) | Updated `_sync_report_artifacts()` to upsert `content_markdown` | Persist markdown to DB |
| [storage/session_store.py:633-659](../../storage/session_store.py#L633-L659) | Updated `list_report_artifacts()` to return `content_markdown`, `eval_runs`, `failed_eval_runs` | Complete API response |
| [storage/session_store.py:661-685](../../storage/session_store.py#L661-L685) | Updated `get_report_artifact()` to return `content_markdown`, `eval_runs`, `failed_eval_runs` | Complete API response |

**session_store touched:** Yes (schema + sync + read methods for `report_artifacts` only).

**No modifications to:** graph, runner, stages, oversight_service, evidence_service, safety_service, eval_service, frontend, Docker, CI, LangGraph adapter.

---

## 3. Key Code Changes

### 3.1 ReportArtifact model — added `content_markdown`
```python
content_markdown: str = ""
```

### 3.2 create_report_artifact — generates markdown
```python
content_md = build_markdown_report(ctx)
artifact = ReportArtifact(..., content_markdown=content_md)
```

### 3.3 session_store — content_markdown in DB
```sql
ALTER TABLE report_artifacts ADD COLUMN IF NOT EXISTS content_markdown TEXT NOT NULL DEFAULT '';
```
Sync: `content_markdown = EXCLUDED.content_markdown`

### 3.4 session_store — list/get return full fields
Both `list_report_artifacts()` and `get_report_artifact()` now return `content_markdown`, `eval_runs`, `failed_eval_runs` in addition to existing fields.

---

## 4. Commands Executed

| Command | Result |
|---------|--------|
| `python -m py_compile api/routers/reports.py` | OK |
| `python -m py_compile core/report_service.py` | OK |
| `python -m py_compile core/models.py` | OK |
| `python -m py_compile core/session_service.py` | OK |
| `python -m py_compile storage/session_store.py` | OK |
| `python -m py_compile scripts/acceptance/ac09b_report_api_persistence.py` | OK |
| `python scripts/acceptance/ac09b_report_api_persistence.py` | 61/61 PASS |

**NOT executed:** pytest, uvicorn, Streamlit, Docker, real PostgreSQL/Redis/LLM/Tavily.

---

## 5. Test / Verification Results

### create report (9/9 PASS)
- report_id starts with "RPT-", version matches, generated_at present
- content_json and content_markdown both present and non-empty (>100 chars each)
- context.report_artifacts count increased (0→1)
- `session_store.save()` called (fake store tracked 2 calls: 1 pre-load + 1 artifact create)
- artifact persisted to fake store

### list reports (7/7 PASS)
- list returns the created artifact with report_id, version, generated_at, content_json, content_markdown
- listed artifact's report_id matches the created one

### get report by id (5/5 PASS)
- retrieved report_id, version match
- content_json and content_markdown present with substantial content

### content_json governance integrity (22/22 PASS)
All 16 top-level governance keys present. Six specific nested field checks:
- `open_actions[0].action_id` = "ACT-SYNTH-001"
- `audit_events[0].event_id` = "AUDIT-SYNTH-001"
- `evidence_sources[0].used_by_failure_mode_ids` = ["FM-001"]
- `safety_findings[0].severity` = "high"
- `eval_cases[0].human_score` = 2
- `eval_runs[0].judge_result` = "failed"

### serialization round-trip (17/17 PASS)
- `model_dump(mode="json")` → 14 keys
- `model_validate(dumped)` succeeds
- All critical fields preserved: report_id, session_id, version, content_markdown
- All nested governance objects survive: actions, audit_events, evidence_sources, safety_findings, eval_cases, eval_runs, stage_readiness, open_risks
- Top-level fields (evidence, open_risks, eval_summary, eval_runs) all preserved

### scope isolation (1/1 PASS)
- No modification to graph/runner/stages/evidence/safety/eval logic

---

## 6. Acceptance Criteria Checklist

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Reports API create/list/get verified in closed loop (fake store + SessionService) | **PASS** |
| 2 | POST create report appends ReportArtifact to session context, triggers save | **PASS** |
| 3 | GET list returns artifact metadata: report_id, version, generated_at | **PASS** |
| 4 | GET by id returns full artifact: content_json + content_markdown | **PASS** |
| 5 | content_json read-back retains actions, audit, evidence, safety, eval, readiness, open risks | **PASS** |
| 6 | ReportArtifact model_dump → model_validate round-trip preserves nested governance fields | **PASS** |
| 7 | No modification to single_step, Review Gate, Stage Gate, PendingHumanAction, Evidence, Safety, Eval logic | **PASS** |
| 8 | No pytest, no service startup, no real external dependencies | **PASS** |

---

## 7. Unresolved Risks (deferred)

1. **Real PostgreSQL persistence**: Fake store used; actual `psycopg` connection and `report_artifacts` table with the new `content_markdown` column not tested against a live DB.
2. **Real Redis cache**: Fake cache used; `ContextCache.set()`/`.get()` round-trip with `model_dump_json()` not tested.
3. **FastAPI TestClient integration**: SessionService tested directly; actual HTTP request/response cycle through the FastAPI router not exercised.
4. **Real four-stage session reports**: Synthetic context only; reports from actual LLM-executed four-stage workflows not tested.
5. **Streamlit report panel**: Frontend integration with reports API not validated.
6. **`content_markdown` column in existing DB**: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is in the CREATE_TABLES_SQL string but not yet executed against any real database.

---

## 8. Recommended Next Step

AC-09B PASSES. Recommended next step: **AC-09C — Real session_store / PostgreSQL report_artifacts minimum persistence verification**, which would:
- Connect to a real PostgreSQL instance and run the CREATE/ALTER TABLE DDL
- Verify `session_store.save()` writes `content_markdown` to the `report_artifacts` table
- Verify `session_store.list_report_artifacts()` and `get_report_artifact()` read back correctly
- Or, if DB coverage is sufficient, proceed to **AC-10 — Streamlit Review Workbench report panel** acceptance.
