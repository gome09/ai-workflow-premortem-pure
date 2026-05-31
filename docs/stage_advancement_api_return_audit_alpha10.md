# Stage Advancement API Return Audit — alpha.10 source-freeze check

Generated: 2026-05-29  
Package stage: `v0.8.0-alpha.10-source-freeze-check`  
Runtime validation: `deferred_by_instruction`

This is a static audit of router source files. It does not call any API endpoint.

## Audit rule

Gate-affecting mutating endpoints should return or contain:

```text
operation
result
stage_id
stage_advancement_decision
next_required_operation
runtime_validation
metadata
```

Read-only endpoints may return domain payloads, but should not invent separate
stage-advancement semantics.

## Router endpoint inventory

| Router File | Method | Path | Function | Gate-affecting | Expected Return | Source-level Note |
|---|---|---|---|---:|---|---|
| `api/routers/chat.py` | `POST` | `/{session_id}` | `send_message` | yes | StageOperationEnvelope or decision-bearing payload | Runs one deterministic workflow turn; stage output, review actions, evidence, safety, or state may change. |
| `api/routers/session.py` | `POST` | `/` | `create_session` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/session.py` | `GET` | `/` | `list_sessions` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/session.py` | `GET` | `/{session_id}` | `get_session` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/session.py` | `POST` | `/{session_id}/materials` | `add_materials` | yes | StageOperationEnvelope or decision-bearing payload | Adds user materials; may add EvidenceSource and SafetyFinding records. |
| `api/routers/session.py` | `POST` | `/{session_id}/flags/resolve` | `resolve_flag` | yes | StageOperationEnvelope or decision-bearing payload | Resolves a governance flag and linked actions. |
| `api/routers/session.py` | `GET` | `/{session_id}/export` | `export_report` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/stage.py` | `GET` | `/{session_id}/stage-readiness` | `list_stage_readiness` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/stage.py` | `GET` | `/{session_id}/stage-readiness/{stage_id}` | `read_stage_readiness` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/stage.py` | `GET` | `/{session_id}/stage-gate/{stage_id}` | `read_stage_gate` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/stage.py` | `GET` | `/{session_id}/stage-resolution` | `list_stage_resolution_operations` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/stage.py` | `GET` | `/{session_id}/stage-resolution/{stage_id}` | `read_stage_resolution_operations` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/stage.py` | `GET` | `/{session_id}/stages/{stage_id}/advancement-decision` | `read_stage_advancement_decision` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/stage.py` | `POST` | `/{session_id}/stages/{stage_id}/advance` | `advance_stage_if_ready` | yes | StageOperationEnvelope or decision-bearing payload | Mutates workflow state only when StageAdvancementDecision allows it. |
| `api/routers/stage.py` | `POST` | `/{session_id}/stages/{stage_id}/rerun` | `prepare_stage_rerun` | yes | StageOperationEnvelope or decision-bearing payload | Stage mutation that supersedes stale actions and refreshes gate state. |
| `api/routers/stage.py` | `POST` | `/{session_id}/stages/{stage_id}/revise` | `request_stage_revision` | yes | StageOperationEnvelope or decision-bearing payload | Stage mutation that prepares regeneration and refreshes gate state. |
| `api/routers/stage.py` | `POST` | `/{session_id}/stages/{stage_id}/rollback` | `request_stage_rollback` | yes | StageOperationEnvelope or decision-bearing payload | Stage mutation that invalidates downstream stages and refreshes gate state. |
| `api/routers/stage.py` | `POST` | `/{session_id}/stages/{stage_id}/sync-review-actions` | `sync_stage_review_actions` | yes | StageOperationEnvelope or decision-bearing payload | Creates missing review actions for blockers. |
| `api/routers/evidence.py` | `GET` | `/{session_id}/evidence` | `list_evidence` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/evidence.py` | `GET` | `/{session_id}/evidence/{evidence_id}` | `get_evidence` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/evidence.py` | `POST` | `/{session_id}/evidence/{evidence_id}/verify` | `verify_evidence` | yes | StageOperationEnvelope or decision-bearing payload | Evidence verification changes evidence_gap gate state. |
| `api/routers/safety.py` | `GET` | `/{session_id}/safety-findings` | `list_safety_findings` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/safety.py` | `POST` | `/{session_id}/safety-findings/{finding_id}/resolve` | `resolve_safety_finding` | yes | StageOperationEnvelope or decision-bearing payload | Safety finding resolution changes safety/final-governance gates. |
| `api/routers/eval.py` | `GET` | `/{session_id}/eval-cases` | `list_eval_cases` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval.py` | `POST` | `/{session_id}/eval-cases/{eval_id}/score` | `score_eval_case` | yes | StageOperationEnvelope or decision-bearing payload | Eval case scoring can change eval_failure gate state. |
| `api/routers/eval.py` | `GET` | `/{session_id}/eval-runs` | `list_eval_runs` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval.py` | `POST` | `/{session_id}/eval-cases/run` | `run_eval_cases` | yes | StageOperationEnvelope or decision-bearing payload | Eval run creation can change Stage 3 eval gate state. |
| `api/routers/eval.py` | `POST` | `/{session_id}/eval-cases/{eval_id}/run` | `run_single_eval_case` | yes | StageOperationEnvelope or decision-bearing payload | Eval run creation can change Stage 3 eval gate state. |
| `api/routers/eval.py` | `GET` | `/{session_id}/eval-judgments` | `list_eval_judgments` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval.py` | `GET` | `/{session_id}/human-calibrations` | `list_human_calibrations` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval.py` | `POST` | `/{session_id}/eval-runs/{run_id}/calibrate` | `calibrate_eval_run` | yes | StageOperationEnvelope or decision-bearing payload | Human calibration can affect eval judgment summaries. |
| `api/routers/eval_datasets.py` | `GET` | `/{session_id}/eval-datasets` | `list_eval_datasets` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_datasets.py` | `POST` | `/{session_id}/eval-datasets` | `create_eval_dataset` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_datasets.py` | `POST` | `/{session_id}/eval-datasets/from-stage3` | `create_eval_dataset_from_stage3` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_datasets.py` | `GET` | `/{session_id}/eval-datasets/{dataset_id}` | `get_eval_dataset` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_datasets.py` | `POST` | `/{session_id}/eval-datasets/{dataset_id}/cases` | `add_eval_dataset_cases` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_datasets.py` | `DELETE` | `/{session_id}/eval-datasets/{dataset_id}/cases` | `remove_eval_dataset_cases` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_datasets.py` | `POST` | `/{session_id}/eval-datasets/{dataset_id}/baseline` | `set_eval_dataset_baseline` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_experiments.py` | `GET` | `/{session_id}/eval-experiments` | `list_eval_experiments` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_experiments.py` | `POST` | `/{session_id}/eval-experiments` | `create_eval_experiment` | yes | StageOperationEnvelope or decision-bearing payload | Creates experiment; affects eval_regression gate. |
| `api/routers/eval_experiments.py` | `GET` | `/{session_id}/eval-experiments/{experiment_id}` | `get_eval_experiment` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_experiments.py` | `POST` | `/{session_id}/eval-experiments/{experiment_id}/run` | `run_eval_experiment` | yes | StageOperationEnvelope or decision-bearing payload | Runs experiment; affects eval_regression gate. |
| `api/routers/eval_experiments.py` | `GET` | `/{session_id}/eval-experiments/{experiment_id}/metrics` | `get_eval_experiment_metrics` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_experiments.py` | `GET` | `/{session_id}/eval-experiments/{experiment_id}/comparison` | `get_eval_experiment_comparison` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/eval_experiments.py` | `POST` | `/{session_id}/eval-experiments/{experiment_id}/comparison` | `compare_eval_experiment` | yes | StageOperationEnvelope or decision-bearing payload | Compares against baseline; affects eval_regression gate. |
| `api/routers/redteam.py` | `GET` | `/{session_id}/redteam/cases` | `list_redteam_cases` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/redteam.py` | `GET` | `/{session_id}/redteam/coverage` | `redteam_coverage_summary` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/redteam.py` | `POST` | `/{session_id}/redteam/generate` | `generate_redteam_cases` | yes | StageOperationEnvelope or decision-bearing payload | Creates RedTeamCase records; affects redteam_coverage gate. |
| `api/routers/redteam.py` | `POST` | `/{session_id}/redteam/cases` | `create_redteam_case` | yes | StageOperationEnvelope or decision-bearing payload | Creates RedTeamCase records; affects redteam_coverage gate. |
| `api/routers/redteam.py` | `POST` | `/{session_id}/redteam/cases/{case_id}/approve` | `approve_redteam_case` | yes | StageOperationEnvelope or decision-bearing payload | Approves RedTeamCase; affects redteam_coverage gate. |
| `api/routers/redteam.py` | `POST` | `/{session_id}/redteam/cases/{case_id}/reject` | `reject_redteam_case` | yes | StageOperationEnvelope or decision-bearing payload | Rejects RedTeamCase; affects redteam_coverage gate. |
| `api/routers/redteam.py` | `POST` | `/{session_id}/redteam/cases/{case_id}/to-eval-case` | `redteam_case_to_eval_case` | yes | StageOperationEnvelope or decision-bearing payload | Syncs RedTeamCase into EvalCase; affects redteam coverage and eval datasets. |
| `api/routers/redteam.py` | `POST` | `/{session_id}/redteam/datasets` | `create_redteam_dataset` | yes | StageOperationEnvelope or decision-bearing payload | Creates redteam_generated EvalDataset; affects redteam_coverage gate. |
| `api/routers/traces.py` | `GET` | `/{session_id}/traces` | `list_traces` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/traces.py` | `GET` | `/{session_id}/traces/{trace_id}` | `get_trace` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/traces.py` | `POST` | `/{session_id}/traces/{trace_id}/to-eval-case` | `trace_to_eval_case` | yes | StageOperationEnvelope or decision-bearing payload | Backfills trace into EvalCase; affects trace_backfill_gap gate. |
| `api/routers/traces.py` | `POST` | `/{session_id}/traces/to-eval-dataset` | `traces_to_eval_dataset` | yes | StageOperationEnvelope or decision-bearing payload | Creates production_trace dataset; affects trace_backfill_gap gate. |
| `api/routers/reports.py` | `POST` | `/{session_id}/reports` | `create_report_artifact` | yes | StageOperationEnvelope or decision-bearing payload | Creates ReportArtifact with stage advancement snapshot. |
| `api/routers/reports.py` | `GET` | `/{session_id}/reports` | `list_report_artifacts` | no | read-only domain payload | Read-only or non-gate endpoint. |
| `api/routers/reports.py` | `GET` | `/{session_id}/reports/{report_id}` | `get_report_artifact` | no | read-only domain payload | Read-only or non-gate endpoint. |

## Specific source-freeze focus

1. `POST /chat/{session_id}` must remain the deterministic workflow turn entrypoint and surface the same stage decision fields used by dedicated stage APIs.
2. Evidence, safety, eval, redteam, trace-backfill, and stage mutation endpoints must not silently mutate gate-relevant state without returning a refreshed advancement view.
3. `StageAdvanceRequest.source` should remain server-owned; public callers must not spoof internal decision sources.
4. Legacy compatibility fields can remain, but the canonical alpha.10 contract is the decision-bearing envelope.

## Deferred validation

The next unified pass must still verify endpoint response schemas with actual FastAPI startup and request execution.
