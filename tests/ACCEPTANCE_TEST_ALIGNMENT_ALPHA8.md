# Alpha.8 Acceptance Test Alignment Notes

Generated/updated for doc-test alignment at: `2026-05-08T14:35:26.657803+00:00`

This file defines how the `tests/` directory should be interpreted for the real alpha.8 codebase.

## Purpose

The alpha.8 acceptance tests must verify that project docs and lightweight contract tests describe the actual source code, not a separately hard-coded narrative.

The source-of-truth files are:

```text
core/stage_advancement_contract.py
core/stage_readiness_service.py
core/stage_resolution_service.py
core/stage_operation_service.py
core/execution_service.py
api/routers/stage.py
graph/transition_policy.py
```

## Current dependency-light acceptance scope

The lightweight acceptance layer may run without FastAPI startup, Streamlit startup, Docker, PostgreSQL, Redis, Tavily, or LLM credentials.

It should verify:

```text
1. Markdown blocker/resolution tables match core/stage_advancement_contract.py.
2. Markdown resolution-operation tables match core/stage_advancement_contract.py.
3. Markdown stage API tables match decorators in api/routers/stage.py.
4. Docs describe evaluate_stage_gate as a read-only gate, not as a mutating runtime chain.
5. Docs preserve the validation boundary: dependency-light contract checks only, full runtime deferred.
6. Tests parse or inspect source-of-truth files instead of comparing one hard-coded doc list with another hard-coded test list.
```

## Prohibited shortcuts

The following must not be used as proof of full alpha.8 behavior:

```text
calling private node/helper functions by hand as the only acceptance path
asserting only that a Markdown list equals a hard-coded expected list
marking dry-run EvalRun plumbing as real target-node execution
calling stage readiness APIs and treating them as mutating repair actions
claiming full pytest/API/Streamlit/Docker/PostgreSQL/Redis/LLM validation without running that stack
```

## Future full-runtime acceptance scope

When the complete dependency and service environment is available, add a separate full-runtime test layer that exercises public entry points:

```text
POST /chat/{session_id}
core.execution_service.execute_one_turn(ctx)
graph.runner.run_one_step(ctx)
graph.langgraph_interrupt_runner.invoke_one_turn_with_interrupts(ctx) only when WORKFLOW_EXECUTION_MODE=langgraph_interrupt
```

That layer should assert:

```text
session persistence
stage output versioning
stage staleness
pending action lifecycle
stage gate results
stage resolution operations
evidence verification effects
safety finding resolution effects
eval case and eval run blocker behavior
report/export governance summary
API response shape
```

## Boundary for this follow-up

This follow-up modifies only Markdown documentation and tests. It does not modify core workflow logic, graph behavior, API behavior, storage behavior, or frontend behavior.
