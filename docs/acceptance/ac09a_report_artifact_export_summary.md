# AC-09A ReportArtifact JSON / Markdown Minimum Export — Acceptance Summary

**Date:** 2026-05-09
**Result:** ALL PASS (70/70 checks, 100%)
**Schema version:** 0.6.0-alpha.8

---

## 1. Current Implementation Observations

### Report-related files

| File | Role |
|------|------|
| [core/report_service.py](../../core/report_service.py) | JSON builder (`build_report_dict`), Markdown builder (`build_markdown_report`), ReportArtifact factory (`create_report_artifact`) |
| [core/models.py](../../core/models.py) | `ReportArtifact` model (lines 371-385), `ProjectContext` model |
| [core/report_diff.py](../../core/report_diff.py) | `build_stage_version_history`, `build_output_diff_summary` |
| [core/eval_service.py](../../core/eval_service.py) | `build_eval_summary` |
| [core/stage_readiness_service.py](../../core/stage_readiness_service.py) | `build_stage_readiness`, `build_unresolved_governance_items` |
| [core/stage_resolution_service.py](../../core/stage_resolution_service.py) | `build_stage_resolution_summary` |
| [core/version.py](../../core/version.py) | `REPORT_SCHEMA_VERSION` |
| [api/routers/reports.py](../../api/routers/reports.py) | 3 endpoints: create, list, get report artifact |

### JSON builder entry: `build_report_dict(ctx)` → 39 top-level keys
### Markdown builder entry: `build_markdown_report(ctx)` → 22 sections (0-19)
### ReportArtifact model fields: `report_id`, `session_id`, `version`, `generated_at`, `ai_generated`, `human_reviewed`, `evidence`, `audit_events`, `open_risks`, `eval_summary`, `eval_runs`, `failed_eval_runs`, `content_json`

---

## 2. Modification Summary

**Production code modified:** YES (minimal markdown report layer only)

| File | Change | Purpose |
|------|--------|---------|
| [core/report_service.py:562-568](../../core/report_service.py#L562-L568) | Added `event.event_id` to audit event markdown display | Audit events now show traceable event_id |
| [core/report_service.py:531-558](../../core/report_service.py#L531-L558) | Expanded unresolved governance section from counts to individual item listings | Human reviewer can see specific eval IDs, safety IDs, blocker messages |

**No modifications to:** graph, runner, stages, evidence/safety logic, eval runner/scoring, Streamlit, Docker, CI, DB migrations.

---

## 3. Key Code Changes

### 3.1 Audit event ID in markdown
```
- `{event.event_id}` {event.created_at.isoformat()} `{event.event_type}` target={event.target_type}/{event.target_id}
```

### 3.2 Unresolved governance items detail in markdown
Section 17 now lists individual items for each category (pending actions, open safety findings, parser errors, unverified evidence, failed eval items, stage blockers), each with their traceable IDs and key attributes.

---

## 4. Commands Executed

| Command | Purpose |
|---------|---------|
| `python -m py_compile core/report_service.py` | PASS |
| `python -m py_compile core/report_diff.py` | PASS |
| `python -m py_compile core/models.py` | PASS |
| `python -m py_compile core/version.py` | PASS |
| `python -m py_compile api/routers/reports.py` | PASS |
| `python -m py_compile scripts/acceptance/ac09a_report_artifact_export.py` | PASS |
| `python scripts/acceptance/ac09a_report_artifact_export.py` | ALL 70 checks PASS |

**NOT executed:** pytest, uvicorn, Streamlit, Docker, real PostgreSQL/Redis/LLM/Tavily connections.

---

## 5. Test / Verification Results

### JSON report field checks (26/26 PASS)
All required top-level fields present: session_id, project_info, ai_generated (stage_1-4), all_actions, open_actions, resolved_actions, audit_events, evidence_sources, safety_findings, eval_cases, eval_runs, eval_summary, stage_readiness, open_risks, schema_version, generated_at, stage_resolution_summary, unresolved_governance_items, stage_lineage, execution_summary, evidence_summary, oversight_summary, report_export_status.

### Markdown report content checks (18/18 PASS)
All 22 markdown sections confirmed accessible; all synthetic governance objects (FM-001, EVID-SYNTH-001, SAFE-SYNTH-001, EVAL-SYNTH-001, RUN-SYNTH-001, ACT-SYNTH-001, ACT-SYNTH-002, AUDIT-SYNTH-001) visible in markdown output.

### EvalCase / EvalRun detail (9/9 PASS)
JSON: eval_id=EVAL-SYNTH-001, human_score=2, passed=False, run_id=RUN-SYNTH-001, judge_result=failed. Markdown: eval IDs visible via stage resolution operations and unresolved governance items.

### Evidence / Safety → risk/blocker linkage (6/6 PASS)
stage_readiness tracks open_safety_finding_ids, safety_finding creates StageBlocker (blocker_type=safety_finding), evidence linked to failure_modes via used_by_failure_mode_ids, stage_readiness shows evidence_gap blocker.

### ReportArtifact versionability (11/11 PASS)
report_id=RPT-xxx, version=0.6.0-alpha.8, generated_at set, content_json contains full report with all sections, evidence/audit_events/eval_runs/open_risks/eval_summary all populated.

### py_compile results
All 6 report-related files compile successfully.

---

## 6. Acceptance Criteria Checklist

| # | Criterion | Result |
|---|-----------|--------|
| 1 | JSON report contains session/project overview, stage outputs, actions, audit events, evidence, safety findings, eval summary, stage readiness, open risks, version, generated_at | **PASS** |
| 2 | Markdown report allows human review of same info, explicitly shows unresolved blocker / open risk | **PASS** |
| 3 | EvalCase/EvalRun shows eval_id, run_id, status, judge_result, human_score (not just raw text) | **PASS** |
| 4 | Evidence/Safety are connected to risks or blockers, not just an appendix | **PASS** |
| 5 | ReportArtifact is versionable: has version, generated_at, artifact identity (report_id) | **PASS** |
| 6 | No modification to single_step main flow, Review Gate, Stage Gate, PendingHumanAction, AuditEvent | **PASS** |

---

## 7. Unresolved Risks (deferred to later AC stages)

1. **API persistence**: ReportArtifact is stored in context list only; no DB table persistence yet (session_store has interface but not yet exercised).
2. **Streamlit report panel**: Frontend report_panel.py integration with these reports not yet validated.
3. **Real-session reports**: Synthetic context only; reports from real 4-stage execution with LLM-generated outputs not tested.
4. **PDF generation**: Explicitly excluded from scope.
5. **Full API startup**: Reports router endpoints not tested with live FastAPI server.

---

## 8. Recommended Next Step

AC-09A PASSES. Recommended next step: **AC-09B — ReportArtifact persistence & reports API minimum acceptance**, which would:
- Verify `POST /sessions/{id}/reports` creates a persisted artifact
- Verify `GET /sessions/{id}/reports` lists artifacts
- Verify `GET /sessions/{id}/reports/{report_id}` retrieves by ID
- Confirm session_store integration for report_artifacts table
