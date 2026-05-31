# Changelog

## v0.8.0-beta.1-local-preview-final — Local Preview Final Acceptance & Real E2E Alignment

Docker-based local-preview acceptance passed, then real E2E validation was completed with live DeepSeek and Tavily connectivity.

### Final Status
- Source version: `0.8.0-alpha.11`
- Release / acceptance label: `v0.8.0-beta.1-local-preview-final`
- Scope: personal and trusted small-team local preview
- Production status: **NOT production-ready**

### Docker Final Acceptance (2026-05-30)
- Docker build (API + frontend): PASS
- PostgreSQL / Redis startup: PASS
- ruff lint / format: PASS
- compileall / version_check: PASS
- Acceptance scripts: PASS — 10 scripts, 615 checks *(historical; final local-preview acceptance: 13 scripts, 707 checks)*
- Full pytest: PASS — 103/103 *(historical; final local-preview acceptance: 148/148)*
- API health / OpenAPI smoke: PASS
- Frontend container smoke: PASS

### Real E2E Results (2026-05-30)
- Low-risk E2E, reading planner: **PASS** — Stage 0–4 complete
- Critical-risk E2E, medication management: **SAFETY_BLOCKED_EXPECTED_FOR_CRITICAL_RISK** — Stage 3 correctly blocked
- DeepSeek real API path: validated
- Tavily real API path: validated

### Bugs Fixed During Acceptance / E2E
- `EvidenceSource` unhashable bug in `stages/stage_1_failure_mode.py` — removed invalid `dict.fromkeys()` usage; 3 regression tests
- Report export `IndexError` in `core/report_service.py:278` — hardened empty/default list indexing; 7 robustness tests
- Stage 3 gate too strict for low-risk projects — added risk-adaptive gate profile; 26 tests and 3 smokes

### Documentation Alignment
- Updated `README.md`, `SECURITY.md`, `docs/current_project_state.md`, `docs/delivery_manifest.md`, and `docs/acceptance/README.md`
- Redacted credential fragments from live E2E report
- Updated example JSON metadata to align with current source version and release label
- Added `LOCAL_PREVIEW_ALIGNMENT_REPORT.md` to describe the documentation-only alignment pass

### Remaining Out of Scope
- Production authentication and RBAC
- Multi-tenant isolation
- Public internet deployment
- Load/concurrency testing
- Production observability and alerting
- Regulated-domain production governance

---

## v0.8.0-beta.1-local-preview — Local Preview Acceptance Closure (Phase 3T Pytest)

Full regression acceptance closure for the local-preview delivery (pytest-only, before Docker Final Acceptance).

### Result
- Full pytest: 103 passed / 0 failed / 0 errors (2.48s)
- Phase 3S target tests: 5/5 passed
- Historical AC-00 ~ AC-11 (v0.6.0-alpha.8): 12/12 PASS
- Conclusion: **PASS**

### Changed (Phase 3S)
- 1 alignment doc file updated
- 2 test files updated (alignment + eval_regression expectations)
- No business code, pyproject.toml, or uv.lock modified

### Added
- `CLAUDE.md` — project state snapshot and constraints for future Claude Code sessions
- `docs/acceptance/current_acceptance_closure_report.md` — acceptance closure report

---

## 0.8.0-alpha.11 freeze-fix — Source Freeze Drift Repair

Source-level freeze-fix patch on top of alpha.10 source-freeze check. No redesign and no v0.9 functionality were introduced.

### Changed
- Updated active package metadata to `v0.8.0-alpha.11-freeze-fix`.
- Replaced active alpha.9 roadmap/status drift with alpha.11 freeze-fix positioning.
- Sourced Eval Regression `policy_version` from `core.version.APP_VERSION`.
- Corrected EvalDataset API return audit semantics: mutating dataset endpoints are gate-affecting because they can unblock or re-block Stage 3 Eval Regression.
- Added frontend StageOperationEnvelope consumption helpers and wired mutating helpers to refresh canonical advancement state.

### Added
- `ALPHA11_FREEZE_FIX.md`.
- `PATCH_MANIFEST_ALPHA11_FREEZE_FIX.md`.
- `FILE_LINK_RECOVERY_ALPHA11_FREEZE_FIX.md`.
- `docs/stage_advancement_api_return_audit_alpha11.md`.
- `docs/stage_advancement_source_freeze_audit_alpha11.md`.
- `scripts/static/stage_advancement_source_freeze_audit.py`.

### Deferred
- pytest, compileall, import smoke, API startup, Streamlit startup, Docker build, database validation, LLM/Search calls, and E2E testing remain deferred.

## 0.8.0-alpha.10 source-freeze-check — v0.9 Entry Gate Artifacts

Source-level artifact patch on top of alpha.10 stage-advancement contract closure. No redesign and no v0.9 functionality were introduced.

### Added
- `ALPHA10_SOURCE_FREEZE_CHECK.md` as the first-step source-freeze summary.
- `docs/stage_advancement_contract_matrix_alpha10.md` generated from the real stage advancement contract source.
- `docs/stage_advancement_api_return_audit_alpha10.md` as a static router return audit.
- `docs/frontend_stage_advancement_consumption_audit_alpha10.md` as a static Streamlit consumption audit.
- `docs/v09_pre_alpha_entry_criteria.md` to define the allowed and prohibited scope for `v0.9.0-pre-alpha.1`.

### Deferred
- pytest, compileall, import smoke, API startup, Streamlit startup, Docker build, database validation, LLM/Search calls, and E2E testing remain deferred.

## 0.8.0-alpha.10 — Stage Advancement Contract Closure

Source-level patch based on the uploaded real `v0.8.0-alpha.9-stage-advancement-hardening` package and the previously approved stage-advancement implementation strategy. No redesign was introduced.

### Changed
- Synchronized `StageBlocker.required_resolution` with `core.stage_advancement_contract.REQUIRED_RESOLUTIONS`, including the concrete Eval Regression operations used by Stage 3 gates.
- Extended `SendMessageResponse` with `stage_advancement_decision`, `next_required_operation`, and `stage_resolution_summary` so chat-driven stage execution exposes the same gate state as dedicated stage APIs.
- Converted materials, flag, evidence, safety, eval-case scoring, eval-case run, and stage mutation flows to return refreshed `StageOperationEnvelope` payloads while preserving domain result fields.
- Ensured all `resolve_action_with_result` outcomes return a latest `StageAdvancementDecision` and `next_required_operation`, not only the resolved path.
- Removed caller-controlled public `StageAdvanceRequest.source`; the service owns `api_advance` for audit integrity.
- Updated version metadata and delivery manifests to alpha.10 and kept runtime validation deferred.

### Deferred
- pytest, API startup, Streamlit startup, Docker build, live LLM/Search calls, and database/runtime integration remain intentionally deferred for the later unified validation pass.

## 0.8.0-alpha.9 — Stage Advancement Hardening

Source-level patch based on the uploaded real `v0.8.0-alpha.8-stage-advancement-prevalidation` package and the previously approved stage-advancement hardening plan. No redesign was introduced.

### Added
- `StageOperationEnvelope` as the standard response envelope for mutating operations that affect stage advancement.
- `build_stage_operation_envelope()` coordinator helper to append refreshed `StageAdvancementDecision` and `next_required_operation`.
- Finer Eval Regression resolution contracts: `create_eval_dataset_from_stage3`, `add_eval_cases_to_dataset`, `set_eval_baseline`, and `create_eval_experiment`.
- Report-level `stage_advancement_decisions_by_stage` and operation executability summary.
- Alpha.9 implementation manifest, hardening note, and download-link recovery guidance.

### Changed
- v0.8 Eval, Red Team, Trace Backfill, calibration, and report-artifact mutating service methods now return alpha.9 advancement envelopes while preserving domain payload fields where possible.
- Eval Regression policy now maps dataset-empty, missing-baseline, and missing-current-experiment states to concrete resolution operations instead of the coarse `run_eval_experiment`.
- Version metadata is aligned to `0.8.0-alpha.9`; runtime validation remains deferred.

### Deferred
- pytest, import smoke, FastAPI startup, Streamlit startup, Docker build, live LLM calls, and live Search calls remain deferred by instruction until unified validation.

## 0.8.0-alpha.1 — Eval Dataset & Experiment Foundation

Source-level patch based on the v0.8-alpha.1 design. Runtime validation remains deferred.

### Added
- EvalDataset, EvalAggregateMetrics, and EvalExperiment models.
- Dataset service for creating datasets manually or from Stage 3 EvalCases.
- Experiment service for creating and running repeatable EvalExperiments.
- Metrics service for pass/fail/needs-review/error aggregation.
- Baseline comparison service with `regression_detected` summary for later gate integration.
- Eval dataset and experiment API routers.
- Storage side tables and migration entry for eval_datasets / eval_experiments / EvalRun experiment linkage.
- Frontend helpers and Streamlit panel additions for dataset/experiment lifecycle.
- Non-executed contract tests for the later unified validation pass.

### Changed
- EvalRun now carries `dataset_id`, `experiment_id`, `run_index`, trace/cost/latency fields.
- Existing EvalCase run flow remains backward-compatible.
- v0.8-alpha.1 comparison summaries do not affect StageAdvancementDecision yet.

### Deferred
- Regression Gate hard blockers are deferred to v0.8-alpha.2.
- RedTeamCase / RedTeamService are deferred to v0.8-alpha.3.
- Taxonomy mapping and Judge/Human Calibration are deferred to later v0.8 milestones.
- pytest, import smoke tests, API startup, Streamlit startup, Docker build, live LLM calls, and live Tavily/search calls remain deferred.


## 0.7.0-alpha.4 — Stage Advancement Hardening

Source-level patch based on the v0.7 stage-advancement hardening strategy. Runtime validation remains deferred.

### Added
- `StageAdvancementDecision` as the unified advance/no-advance contract for graph/API/frontend/report consumers.
- `core.stage_advancement_coordinator` to coordinate gate evaluation, resolution operations, action sync, stage mutation summaries, and trace records.
- API endpoints:
  - `GET /sessions/{session_id}/stages/{stage_id}/advancement-decision`
  - `POST /sessions/{session_id}/stages/{stage_id}/advance`
- Action and stage-operation trace categories: `action` and `stage_operation`.
- Non-executed contract test placeholders for the later unified validation pass.

### Changed
- Graph review approval now uses `StageAdvancementDecision` instead of interpreting `StageGateResult` directly.
- Action resolution, evidence verification, safety finding resolution, rerun, revise, rollback, and review-action sync now refresh or record advancement decisions.
- Remaining legacy GateRule wrappers were migrated to direct rule classes while preserving the public blocker semantics.
- Frontend gate/action components expose decision source, lifecycle, hard blocker counts, executable operation counts, idempotency keys, and superseded status.

### Deferred
- pytest, import smoke tests, API startup, Streamlit startup, Docker build, live LLM calls, and live Tavily/search calls.
- v0.8 EvalDataset/EvalExperiment/RedTeamCase work.
- v0.9 Workspace/RBAC/Claim-Evidence/Report Center work.


## 0.7.0-alpha.3 — Stage Advancement Finalization

Source-level patch based on the v0.7 stage-advancement strategy. Runtime validation is deferred.

### Changed
- Unified release metadata to 0.7.0-alpha.3 while preserving ProjectContext/ACTION schema version 0.7.0.
- Migrated the first four core GateRules away from CollectorGateRule wrappers: missing_output, stale_dependency, action_state, parser_error.
- Added explicit action-resolution contract documentation for stale/conflict/replay/hash semantics.
- Added provider-neutral structured-output boundary files under core/llm.
- Added stage-advancement summary to generated reports.
- Added minimal Streamlit gate/trace panel components and trace client helper.
- Updated download-link recovery instructions for the alpha.3 package.

### Deferred
- pytest, API startup, Streamlit startup, Docker build, live LLM calls, and live Tavily/search calls.
- v0.8 EvalDataset/EvalExperiment/RedTeamCase work.
- v0.9 Workspace/RBAC/Claim-Evidence/Report Center work.


## 0.7.0-alpha.2 — Stage Advancement Closure Patch

Added:
- `ActionResolutionResult` to make human action outcomes explicit.
- `stale` human action status for old stage-version submissions.
- Service/API access to `action_resolution_logs`.
- Trace metadata fields (`trace_type`, `metadata`) for parser/action/gate coordination.
- Structured output result states for `validation_failed`, `non_json`, and `markdown_fallback`.
- v0.7 migration fixtures and non-executed test placeholders.

Changed:
- Stage1-4 JSON-first parsing now enters through `StructuredOutputClient`.
- Oversight API can return clear stale/conflict/validation_failed/idempotent_replay semantics.
- GateRule base contract is explicit while legacy collector compatibility is retained.
- Version metadata is aligned to the v0.7 reliable-execution line.

Deferred:
- pytest/runtime validation;
- API and Streamlit startup checks;
- Docker build;
- external LLM/search validation.

# Changelog
## 0.6.0-alpha.8+opensource-repair

- Re-ran and passed source-level validation: dependency sync, Ruff lint/format, compileall, version metadata check, and 71 pytest cases.
- Applied Ruff formatting and lint cleanup across runtime, frontend, tests, and scripts.
- Added `uv.lock` for reproducible dependency resolution.
- Added minimal GitHub Actions CI for lint and tests.
- Added `.dockerignore` and updated Dockerfile to use the checked-in lockfile.
- Filled intentionally empty placeholder modules with explanatory docstrings.
- Updated README, package manifest, and delivery notes to reflect the current validation state.
## v0.6.0-alpha.8-doc-test-core-alignment-followup

- Added `docs/v0_6_0_alpha_8_core_code_alignment_contract.md`.
- Added `tests/ACCEPTANCE_TEST_ALIGNMENT_ALPHA8.md`.
- Added `tests/test_alpha8_doc_core_alignment_contract.py`.
- Updated current docs to distinguish source-level doc/test/core contract validation from full runtime validation.
- The new contract test parses source-of-truth files instead of comparing hard-coded Markdown/test lists.
- No core workflow/API/graph/storage/frontend code was modified by this follow-up.
## v0.6.0-alpha.8-doc-test-alignment

- Updated current docs to match alpha.8 stage gate behavior and execution-service dispatch.
- Expanded README API list to match current routers.
- Normalized validation wording: full runtime/full pytest deferred; dependency-light alpha.8 subset validated.
- Preserved `FailureMode.id` in context summaries for traceability.
- Aligned interrupt-record tests with current pending-to-resolved lifecycle.
- Added dependency guards for API/storage tests in lightweight environments.
- No workflow redesign.
## v0.6.0-alpha.8-doc-config-cleanup

- Updated current alpha.8 documentation entry points for open-source release readiness.
- Added `docs/README.md` to separate current docs from historical docs.
- Fixed `scripts/version_check.py` README status version regex.
- Cleaned stale alpha.6/alpha.7 explanatory wording in comments/UI text.
- No business-logic redesign and no runtime validation.
## v0.6.0-alpha.7

- Stage Advancement Operation Hardening patch.
- Adds `core/stage_scope_service.py`.
- Hardens current-stage operation scope, pending-only action API binding, structured edit requirements, evidence resolution semantics, and final governance alignment.
- Runtime validation remains deferred by instruction.
## 0.6.0-alpha.6 - Stage Advancement Contract Closure Patch

- Regenerated from the real uploaded `v0.6.0-alpha.5` source.
- Added `core/stage_resolution_service.py` with `StageResolutionOperation`.
- Extended `core/stage_advancement_contract.py` with `RESOLUTION_OPERATION_CONTRACT`.
- Added read-only APIs for stage gate and stage resolution operations.
- Extended report output with `stage_resolution_summary` and `next_required_operation`.
- Added operation cards to the Streamlit Stage Gate panel.
- Added `StageMutationResult` to document edit/revise/rollback lineage effects without breaking existing return contracts.
- Updated `core/__init__.py` to avoid eager settings import during lightweight model/service imports.
- Added alpha.6 docs, static scenario file, and deferred pytest contract tests.
- No pytest, service startup, Docker, or runtime validation was performed by instruction.
## 0.6.0-alpha.5 - Stage Advancement Contract Hardening Patch

- Regenerated from the real uploaded `v0.6.0-alpha.4` source.
- Added `core/stage_advancement_contract.py` with explicit blocker/action/resolution semantics.
- Added `core/stage_revision_service.py` for dependency lineage, stale downstream stages, revise, and rollback bookkeeping.
- Extended `ProjectContext` with `stage_dependency_versions` and `stage_staleness`.
- Added `missing_stage_output` and `stale_dependency` blockers plus `run_stage` and `rerun_stage` required resolutions.
- Added `stage_lifecycle` and dependency metadata to readiness output.
- Updated `graph.nodes` approval flow to return the full blocker list instead of only the first blocker reason.
- Updated edit/revise/back handling to mark downstream stages stale and supersede stale actions.
- Updated report output with stage lineage, stale-stage metadata, and `report_export_status`.
- No pytest, service startup, Docker, or runtime validation was performed by instruction.
## 0.6.0-alpha.4 - Stage Advancement Contract Patch

- Bumped source/report/package metadata to `0.6.0-alpha.4`.
- Added unified `core/stage_readiness_service.py` with `StageBlocker`, `StageGateResult`, and `StageReadiness`.
- Made `graph.transition_policy.stage_can_continue()` delegate to the unified gate result while preserving its tuple return contract.
- Added read-only stage readiness APIs under `/sessions/{session_id}/stage-readiness`.
- Updated reports to use the same readiness/governance summary source as the transition policy.
- Added a Streamlit sidebar blocker panel that shows blocker type, severity, action_id, required resolution, and next operations.
- Added an execution-layer `sync_execution_after_stage_revision()` coordination hook for future interrupt sync after stage revision/supersede.
- Kept `single_step` as the default path and kept `langgraph_interrupt` experimental.
- Runtime validation and pytest remain deferred by instruction.
## 0.6.0-alpha.3 - Stage-Control Stabilization Patch

- Bumped source/report/package metadata to `0.6.0-alpha.3`.
- Centralized execution-mode synchronization after human action resolution in `core/execution_service.py`.
- Removed direct `graph.interrupts` calls from `core/oversight_service.py`.
- Updated evidence, flag, and safety resolution paths so indirectly resolved actions can be synchronized by the session/execution layer.
- Strengthened `graph/transition_policy.py` with parser-error, safety-finding, evidence-readiness, policy-coverage, high-risk eval, and final governance gates.
- Added Stage 2 high-risk failure-mode coverage gap detection in `tools/safety_classifier.py`.
- Added report `stage_readiness` and `unresolved_governance_items` sections.
- Added `docs/stage-transition-policy.md` and `docs/v0_6_0_alpha_3_stabilization.md`.
- Updated README, ROADMAP, PACKAGE_MANIFEST, and the stale `tests/test_session_service.py` patch target.
- Runtime validation and pytest remain deferred by instruction.
## 0.6.0-alpha.2 - Checkpoint Interrupt Adapter Source Patch

- Added `graph/interrupt_gate.py` for side-effect-light LangGraph review pauses.
- Reworked `graph/langgraph_interrupt_runner.py` into a one-turn experimental runner.
- Wired `WORKFLOW_EXECUTION_MODE=langgraph_interrupt` through `core/execution_service.py`.
- Added action resolution resume consumption via `Command(resume=...)` in `core/session_service.py`.
- Added `/health` execution mode and adapter status metadata.
- Updated reports with `adapter_level`, consumed resume count, pending resume count, and resume error count.
- Updated Streamlit interrupt debug visibility for resumed-but-unconsumed and cancelled records.
- Preserved `single_step` as the default path and deferred full pytest/runtime validation.
## 0.6.0-alpha.1 - Interrupt Adapter Mapping Patch

- Extended `InterruptRecord` for v0.6 adapter metadata.
- Added action/interrupt resume-cancel consistency checks.
- Added read-only interrupt records API.
- Added report and Streamlit interrupt visibility.
- Preserved `single_step` as the default execution path.

v0.5.1-alpha

- Added raw output persistence guard for parser failure paths.
- Added explicit EvalRun judge mode and violated criteria.
- Added severity-aware evidence coverage actions and report summaries.
- Added execution service and interrupt adapter foundations while keeping single_step as default.
## 0.5.0-alpha

- Added `EvalRun` model and `ProjectContext.eval_runs`.
- Added `core/eval_runner.py` with manual, dry_run, and llm_node run modes.
- Added eval run APIs: list runs, run all cases, run one case.
- Added `eval_runs` table and persistence sync.
- Updated Stage 3 to prompt for multi-node coverage.
- Added Review Gate actions for failed EvalCase and EvalRun records.
- Extended JSON and Markdown reports with EvalRun data.
- Updated Streamlit Eval panel with run controls.
- Added LICENSE, SECURITY.md, CONTRIBUTING.md, and ROADMAP.md.
## 0.4.1-alpha

- Closed out evidence, safety, report artifact, and coverage summary foundations.

## v0.8.0-alpha.3 Red Team Foundation

- Added RedTeamCase model and ProjectContext redteam state.
- Added deterministic RedTeamService generation from high-risk SafetyFinding, FailureMode, and WorkflowNode signals.
- Added RedTeamCase approval/rejection and RedTeamCase-to-EvalCase sync.
- Added redteam_generated EvalDataset creation.
- Added Stage 3 `redteam_coverage` GateRule before `eval_regression`.
- Added Red Team API router and minimal Streamlit panel.
- Added Red Team coverage summary to reports.
- Added redteam_cases storage side table and migration entry.
- Added alpha3 test source files; runtime validation remains deferred.
