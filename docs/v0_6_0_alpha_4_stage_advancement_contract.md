# v0.6.0-alpha.4 Stage Advancement Contract

This document records the alpha.4 implementation scope. It is based on the real v0.6.0-alpha.3 source and does not redesign the product.

## Phase objective

The project is still in the v0.6 alpha line. The next stage is not v0.7 and not production readiness. The objective is to make phase advancement explicit and shared:

```text
stage executor
→ review gate
→ PendingHumanAction
→ StageGateResult / StageBlocker
→ transition policy
→ stage readiness
→ next stage / complete
```

## New contract

`core/stage_readiness_service.py` introduces:

- `StageBlocker`: structured reason that a stage cannot advance.
- `StageGateResult`: machine-readable gate result for one stage.
- `StageReadiness`: read-only API/report/frontend view.

`graph.transition_policy.stage_can_continue(ctx, stage)` remains backward-compatible and delegates to the unified service.

## Non-goals

- No pytest/runtime validation in this patch.
- No default switch to `langgraph_interrupt`.
- No React rewrite.
- No PDF export.
- No Alembic migration.

## Stage-specific rules

### Stage 1

High/critical failure modes must have evidence references and those evidence sources must be verified. Dismissing a verification action closes the action for audit purposes but does not mark the evidence as verified and therefore does not remove the evidence gate.

### Stage 2

High/critical failure modes from Stage 1 must be covered by workflow nodes, and nodes that cover them must include `HumanOversightPolicy`.

### Stage 3

Failed EvalCase/EvalRun records for high-risk nodes remain blockers until handled by approve/edit action. Coverage gaps are exposed as readiness warnings in alpha.4 and are not yet hard blockers.

### Stage 4

Final governance summarizes open critical safety findings, parser errors, pending blocking actions, unverified high-risk evidence, and failed high-risk eval items.

## API

Read-only stage readiness endpoints:

```text
GET /sessions/{session_id}/stage-readiness
GET /sessions/{session_id}/stage-readiness/{stage_id}
```

These endpoints do not run LLM calls, do not advance state, and do not mutate project context.
