# AC-09B-FIX Reports Router TestClient — Acceptance Summary

**Date:** 2026-05-09
**Result:** ALL PASS (53/53 checks, 100%)
**Schema version:** 0.6.0-alpha.8

---

## 1. Current Implementation Observations

### Reports router (`api/routers/reports.py`)

| Route | Method | Handler | Delegates to |
|-------|--------|---------|-------------|
| `/sessions/{session_id}/reports` | POST | `create_report_artifact` | `session_service.create_report_artifact()` |
| `/sessions/{session_id}/reports` | GET | `list_report_artifacts` | `session_service.list_report_artifacts()` |
| `/sessions/{session_id}/reports/{report_id}` | GET | `get_report_artifact` | `session_service.get_report_artifact()` |

### App registration (`api/main.py:48`)
```python
app.include_router(reports.router)
```
Router is registered at `/sessions` prefix (defined in the router itself via `APIRouter(prefix="/sessions")`).

### Dependency wiring
The router imports `session_service` as a module-level singleton:
```python
from core.session_service import session_service
```
No FastAPI `Depends()` injection — handlers call the singleton directly. The `session_service` uses `session_store` and `context_cache` from `storage/` module-level singletons.

### Response JSON shape (POST/GET by id)
```json
{
  "report_id": "RPT-xxxxxxxx",
  "session_id": "...",
  "version": "0.6.0-alpha.8",
  "generated_at": "2026-05-09T...",
  "content_json": { ... 39 keys ... },
  "content_markdown": "# AI Workflow Pre-mortem Report\n...",
  "ai_generated": { ... },
  "evidence": [ ... ],
  "audit_events": [ ... ],
  "open_risks": [ ... ],
  "eval_summary": { ... },
  "eval_runs": [ ... ],
  "failed_eval_runs": [ ... ]
}
```

---

## 2. Modification Summary

**无生产代码修改** (No production code modifications).

All 4 files checked remained unchanged:
- `api/routers/reports.py` — no changes
- `api/main.py` — no changes
- `core/session_service.py` — no changes
- `core/report_service.py` — no changes

The HTTP layer worked correctly as-is. The only new artifact is the acceptance script itself.

---

## 3. Key Code Changes

None. The reports router, session_service, and FastAPI app required zero changes to pass TestClient validation.

---

## 4. Commands Executed

| Command | Result |
|---------|--------|
| `python -m py_compile api/routers/reports.py` | OK |
| `python -m py_compile api/main.py` | OK |
| `python -m py_compile core/session_service.py` | OK |
| `python -m py_compile scripts/acceptance/ac09b_fix_reports_router_testclient.py` | OK |
| `python scripts/acceptance/ac09b_fix_reports_router_testclient.py` | 53/53 PASS |

**NOT executed:** pytest, uvicorn, Streamlit, Docker, real PostgreSQL/Redis/LLM/Tavily.

---

## 5. Test / Verification Results

### POST /sessions/{id}/reports (10/10 PASS)
- HTTP 200
- `report_id` = "RPT-4b0bf24e" (starts with RPT-)
- `version` = "0.6.0-alpha.8"
- `generated_at` present
- `content_json` present (39 keys)
- `content_markdown` present and substantial (>100 chars)
- `save_session` called (fake store: 1→2 calls)
- Artifact persisted to fake store (0→1)
- `context.report_artifacts` count = 1

### GET /sessions/{id}/reports (8/8 PASS)
- HTTP 200
- Returns list with 1 artifact
- `report_id` matches created artifact
- `version`, `generated_at`, `content_json`, `content_markdown` all present

### GET /sessions/{id}/reports/{report_id} (33/33 PASS)
- HTTP 200
- `report_id`, `version`, `generated_at` match
- `content_json` + `content_markdown` present and substantial
- All 16 governance keys in content_json: actions, open_actions, resolved_actions, audit_events, evidence_sources, safety_findings, eval_cases, eval_runs, eval_summary, stage_readiness, open_risks, unresolved_governance_items, stage_resolution_summary, evidence_summary, oversight_summary, schema_version
- Nested field values: action_id=ACT-001, event_id=AUDIT-001, judge_result=failed, severity=high, open_risks count=1
- Markdown sections: Pending/Human Actions, Safety, Eval, Audit, Risk all present

### Error handling (2/2 PASS)
- GET non-existent report → 404
- POST non-existent session → 404

### Scope isolation (1/1 PASS)
- No production code modified

### py_compile (4/4 PASS)
- All 4 files compile cleanly

---

## 6. Acceptance Criteria Checklist

| # | Criterion | Result |
|---|-----------|--------|
| 1 | TestClient successfully calls reports router create/list/get | **PASS** |
| 2 | POST create returns ReportArtifact, triggers save path | **PASS** |
| 3 | GET list sees created artifact via HTTP layer | **PASS** |
| 4 | GET by report_id reads back full artifact via HTTP layer | **PASS** |
| 5 | HTTP response includes content_json and content_markdown | **PASS** |
| 6 | content_json governance fields complete (actions, audit, evidence, safety, eval, readiness, open risks) | **PASS** |
| 7 | No modification to single_step, Review Gate, Stage Gate, PendingHumanAction, Evidence, Safety, Eval logic | **PASS** |
| 8 | No pytest, no service startup, no real external dependencies | **PASS** |

---

## 7. Unresolved Risks (deferred)

1. **Real PostgreSQL DDL execution**: `ALTER TABLE report_artifacts ADD COLUMN content_markdown` not yet executed against any live database.
2. **Real Redis round-trip**: `ContextCache.set()`/`.get()` with `model_dump_json()` not tested against Redis.
3. **Real four-stage session reports**: Synthetic context only.
4. **Lifespan DB initialization**: `session_store.initialize()` was skipped via fake store; real DB table creation path not tested.
5. **Streamlit report panel**: Frontend integration not validated.

---

## 8. Recommended Next Step

AC-09B-FIX PASSES. The HTTP layer is confirmed working end-to-end. Recommended: **AC-09C Real PostgreSQL report_artifacts minimum persistence verification** — execute DDL against a real PG instance, verify `_sync_report_artifacts()` writes `content_markdown`, verify read-back through `list_report_artifacts()`/`get_report_artifact()`.
