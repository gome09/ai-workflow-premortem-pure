# v0.6.0-alpha.8 Core-Code Alignment Contract

Generated/updated for doc-test alignment at: `2026-05-08T14:35:26.657803+00:00`

This document is an acceptance-oriented map between the Markdown docs, the tests under `tests/`, and the real alpha.8 source code. It does **not** redesign the project and does **not** claim full runtime validation.

## Non-redesign boundary

This follow-up is limited to documentation and test-code alignment.

```text
Allowed:  Markdown docs, test documentation, dependency-light contract tests
Forbidden: core workflow logic changes, API behavior changes, graph behavior changes, storage behavior changes
```

The source-of-truth implementation remains:

```text
core/stage_advancement_contract.py
core/stage_readiness_service.py
core/stage_resolution_service.py
core/stage_operation_service.py
core/execution_service.py
api/routers/stage.py
graph/transition_policy.py
```

## What the current dependency-light tests can prove

The dependency-light contract tests can prove that docs and acceptance notes match the source-level contracts that are safe to inspect without starting FastAPI, Streamlit, Docker, PostgreSQL, Redis, Tavily, or an LLM.

They can prove:

```text
blocker type -> required resolution mappings
required resolution -> API operation metadata mappings
stage router method/path declarations
stage gate collector coverage described by docs
validation wording does not claim full runtime validation
```

They cannot prove:

```text
FastAPI app startup
Streamlit app startup
Docker compose startup
real LLM calls
Tavily calls
PostgreSQL persistence
Redis cache behavior
LangGraph checkpoint runtime behavior
end-to-end workflow replay behavior
```

## Authoritative blocker to resolution matrix

This table must match `STAGE_ADVANCEMENT_CONTRACT` in `core/stage_advancement_contract.py`.

| Blocker type | Required resolution | Approval override allowed | Core source |
|---|---|---:|---|
| `missing_stage_output` | `run_stage` | `false` | `core/stage_advancement_contract.py` |
| `stale_dependency` | `rerun_stage` | `false` | `core/stage_advancement_contract.py` |
| `pending_action` | `resolve_action` | `false` | `core/stage_advancement_contract.py` |
| `rejected_action` | `revise_stage` | `false` | `core/stage_advancement_contract.py` |
| `unresolved_escalation` | `approve_escalation` | `false` | `core/stage_advancement_contract.py` |
| `parser_error` | `edit_stage_output` | `false` | `core/stage_advancement_contract.py` |
| `safety_finding` | `resolve_safety_finding` | `true` | `core/stage_advancement_contract.py` |
| `evidence_gap` | `verify_evidence` | `false` | `core/stage_advancement_contract.py` |
| `policy_gap` | `edit_stage_output` | `false` | `core/stage_advancement_contract.py` |
| `eval_failure` | `resolve_action` | `true` | `core/stage_advancement_contract.py` |
| `redteam_coverage` | `generate_redteam_cases` | `false` | `core/stage_advancement_contract.py` |
| `eval_regression` | `create_eval_experiment` | `false` | `core/stage_advancement_contract.py` |
| `trace_backfill_gap` | `trace_to_eval_case` | `false` | `core/stage_advancement_contract.py` |
| `final_governance` | `resolve_safety_finding` | `true` | `core/stage_advancement_contract.py` |

## Authoritative resolution operation matrix

This table must match `RESOLUTION_OPERATION_CONTRACT` in `core/stage_advancement_contract.py`.

| Required resolution | API-capable contract | API method | API path template |
|---|---:|---|---|
| `run_stage` | `false` | `` | `` |
| `rerun_stage` | `true` | `POST` | `/sessions/{session_id}/stages/{stage_id}/rerun` |
| `resolve_action` | `true` | `POST` | `/sessions/{session_id}/actions/{action_id}/resolve` |
| `verify_evidence` | `true` | `POST` | `/sessions/{session_id}/evidence/{evidence_id}/verify` |
| `edit_stage_output` | `true` | `POST` | `/sessions/{session_id}/actions/{action_id}/resolve` |
| `revise_stage` | `true` | `POST` | `/sessions/{session_id}/stages/{stage_id}/revise` |
| `back_stage` | `true` | `POST` | `/sessions/{session_id}/stages/{stage_id}/rollback` |
| `approve_escalation` | `true` | `POST` | `/sessions/{session_id}/actions/{action_id}/resolve` |
| `resolve_safety_finding` | `true` | `POST` | `/sessions/{session_id}/safety-findings/{finding_id}/resolve` |
| `create_eval_dataset_from_stage3` | `true` | `POST` | `/sessions/{session_id}/eval-datasets/from-stage3` |
| `add_eval_cases_to_dataset` | `true` | `POST` | `/sessions/{session_id}/eval-datasets/{dataset_id}/cases` |
| `set_eval_baseline` | `true` | `POST` | `/sessions/{session_id}/eval-datasets/{dataset_id}/baseline` |
| `create_eval_experiment` | `true` | `POST` | `/sessions/{session_id}/eval-experiments` |
| `run_eval_experiment` | `true` | `POST` | `/sessions/{session_id}/eval-experiments/{experiment_id}/run` |
| `compare_eval_experiment` | `true` | `POST` | `/sessions/{session_id}/eval-experiments/{experiment_id}/comparison` |
| `generate_redteam_cases` | `true` | `POST` | `/sessions/{session_id}/redteam/generate` |
| `approve_redteam_case` | `true` | `POST` | `/sessions/{session_id}/redteam/cases/{case_id}/approve` |
| `sync_redteam_eval_case` | `true` | `POST` | `/sessions/{session_id}/redteam/cases/{case_id}/to-eval-case` |
| `create_redteam_dataset` | `true` | `POST` | `/sessions/{session_id}/redteam/datasets` |
| `trace_to_eval_case` | `true` | `POST` | `/sessions/{session_id}/traces/{trace_id}/to-eval-case` |
| `create_trace_backfill_dataset` | `true` | `POST` | `/sessions/{session_id}/traces/to-eval-dataset` |

## Actual stage gate collector coverage

`core/stage_readiness_service.evaluate_stage_gate(ctx, stage)` is the authoritative read-only gate. The implementation evaluates common blockers first, then stage-specific blockers.

| Scope | Collector | Meaning |
|---|---|---|
| common | `_collect_missing_output_blockers` | Stage output must exist before advancement. |
| common | `_collect_stale_dependency_blockers` | Stage output cannot rely on stale upstream stage versions. |
| common | `_collect_action_state_blockers` | Pending, rejected, and unresolved escalation actions are blockers. |
| common | `_collect_parser_blockers` | Parser errors require structured stage-output repair. |
| common | `_collect_safety_blockers` | Open high/critical safety findings requiring review block advancement. |
| stage 1 | `_collect_stage1_evidence_blockers` | High/critical failure modes require existing verified evidence references. |
| stage 2 | `_collect_stage2_policy_blockers` | High/critical failure modes require WorkflowNode coverage and oversight policy. |
| stage 3 | `_collect_stage3_eval_blockers` | High-risk workflow nodes require EvalCase coverage; failed/needs_review evals block. |
| stage 4 | `_collect_stage4_final_blockers` | Final governance wraps unresolved upstream hard blockers, parser errors, and safety findings. |

The docs should describe these as a gate/collector contract, not as a single runtime chain. The gate is read-only; mutation happens only through explicit services such as `core/stage_operation_service.py`, human-action resolution, evidence verification, or safety-finding resolution.

## Authoritative stage API surface

This table must match decorator declarations in `api/routers/stage.py`.

| Method | Path | Router function |
|---|---|---|
| `GET` | `/sessions/{session_id}/stage-readiness` | `list_stage_readiness` |
| `GET` | `/sessions/{session_id}/stage-readiness/{stage_id}` | `read_stage_readiness` |
| `GET` | `/sessions/{session_id}/stage-gate/{stage_id}` | `read_stage_gate` |
| `GET` | `/sessions/{session_id}/stage-resolution` | `list_stage_resolution_operations` |
| `GET` | `/sessions/{session_id}/stage-resolution/{stage_id}` | `read_stage_resolution_operations` |
| `POST` | `/sessions/{session_id}/stages/{stage_id}/rerun` | `prepare_stage_rerun` |
| `POST` | `/sessions/{session_id}/stages/{stage_id}/revise` | `request_stage_revision` |
| `POST` | `/sessions/{session_id}/stages/{stage_id}/rollback` | `request_stage_rollback` |
| `GET` | `/sessions/{session_id}/stages/{stage_id}/advancement-decision` | `read_stage_advancement_decision` |
| `POST` | `/sessions/{session_id}/stages/{stage_id}/advance` | `advance_stage_if_ready` |
| `POST` | `/sessions/{session_id}/stages/{stage_id}/sync-review-actions` | `sync_stage_review_actions` |

## Current execution-path statement

The stable path remains:

```text
WORKFLOW_EXECUTION_MODE=single_step
FastAPI / Streamlit
-> SessionService
-> core.execution_service.execute_one_turn(ctx)
-> graph.runner.run_one_step(ctx)
-> graph.nodes
```

The optional experimental path remains:

```text
WORKFLOW_EXECUTION_MODE=langgraph_interrupt
FastAPI / Streamlit
-> SessionService
-> core.execution_service.execute_one_turn(ctx)
-> graph.langgraph_interrupt_runner.invoke_one_turn_with_interrupts(ctx)
```

Docs and tests must not present `langgraph_interrupt` as the default path.

## Acceptance wording required for this package

Use this wording when describing the validation state:

```text
Dependency-light alpha.8 doc/test/core contract checks are validated.
Full runtime validation remains deferred until the full dependency and service environment is available.
```

Do not replace it with any of the following unless those checks have actually run:

```text
full pytest passed
API startup passed
Streamlit startup passed
Docker compose passed
PostgreSQL integration passed
Redis integration passed
real LLM replay passed
end-to-end workflow validation passed
```

## Future full-runtime acceptance requirements

A later full-runtime validation package should add tests that execute the public workflow entry points rather than private implementation shortcuts:

```text
POST /chat/{session_id}
or core.execution_service.execute_one_turn(ctx)
or graph.runner.run_one_step(ctx) for the stable single_step path
or graph.langgraph_interrupt_runner.invoke_one_turn_with_interrupts(ctx) for the explicit experimental path
```

It should assert persisted session state, stage readiness, stage resolution operations, pending-action transitions, report output, and API responses in the full dependency environment.
