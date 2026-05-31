# Architecture

This project is an AI Workflow Pre-mortem & Human Oversight Tool, not a general workflow builder.

## Runtime Path

Current request execution flows through `SessionService` and the execution-mode coordinator before entering the graph runner:

```text
FastAPI / Streamlit
-> SessionService
-> core.execution_service.execute_one_turn(ctx)
   -> single_step
      -> graph.runner.run_one_step(ctx)
   -> langgraph_interrupt experimental mode
      -> graph.langgraph_interrupt_runner.invoke_one_turn_with_interrupts(ctx)
-> graph.nodes
-> StageExecutor
-> Review Gate
-> PendingHumanAction / SafetyFinding / EvidenceSource / EvalCase / EvalRun
-> PostgreSQL + Redis cache
```

`single_step` remains the default stable path. `langgraph_interrupt` is an experimental adapter path selected only through `WORKFLOW_EXECUTION_MODE=langgraph_interrupt`.

## Review and Action Resolution Path

Human review actions are resolved through service-layer coordination rather than by support modules advancing stages directly:

```text
FastAPI / Streamlit
-> SessionService
-> core.oversight_service.resolve_action(...)
-> graph.transition_policy.evaluate_action_resolution(...)
-> core.execution_service.sync_execution_after_action_resolution(...)
   -> single_step: no checkpoint mutation
   -> langgraph_interrupt: mark interrupt resumed/cancelled and consume resume once
-> stage gate re-evaluation
```

Stage rerun, revise, rollback, and sync-review-actions are explicit stage operations under `core.stage_operation_service` and `api.routers.stage`.

## Core Principles

- Workflow transitions are deterministic and code-controlled.
- LLMs generate analysis, not autonomous workflow transitions.
- High-risk decisions require human review.
- Evidence, safety findings, eval cases, eval runs, interrupt records, and report artifacts are first-class records.
- Graph, API, frontend, and reports consume the same stage readiness contract.
- Full runtime validation is intentionally separate from dependency-light contract tests.

## Current alpha.8 coordination points

- `core/version.py` is the version source of truth.
- `core/stage_readiness_service.py` is the authoritative stage gate source.
- `graph/transition_policy.py` keeps backward-compatible transition and action-resolution helpers.
- `core/stage_resolution_service.py` maps blockers to concrete next operations.
- `core/stage_operation_service.py` performs explicit non-runtime stage operations.
- `core/execution_service.py` centralizes execution-mode dispatch and interrupt synchronization.
- `FailureMode.evidence_ids` preserves structured evidence references.
- User materials are represented as `EvidenceSource(source_type="user_material")`.
- Eval coverage and high-risk eval review are part of the Stage 3 gate.


## Doc/Test/Core Alignment Contract

The current dependency-light acceptance layer is documented in:

```text
docs/v0_6_0_alpha_8_core_code_alignment_contract.md
tests/ACCEPTANCE_TEST_ALIGNMENT_ALPHA8.md
tests/test_alpha8_doc_core_alignment_contract.py
```

These checks parse or inspect the source-of-truth files instead of comparing one hard-coded documentation list with another hard-coded test list. They verify source-level contracts such as blocker mappings, resolution-operation mappings, stage router declarations, and validation-boundary wording.

They do not replace full runtime validation. FastAPI startup, Streamlit startup, Docker compose, PostgreSQL, Redis, Tavily, real LLM calls, and end-to-end workflow replay still require the full dependency/service environment.
