# Human Oversight Core v0.2-alpha

This patch upgrades the existing `FlaggedItem + review text` mechanism into a first-class human oversight queue.

## Added modules

- `core/audit_service.py`
- `core/oversight_service.py`
- `graph/review_gate.py`
- `api/routers/oversight.py`

## Main behavior

1. Stage executors still run through the existing single-step runner.
2. After a stage executor finishes, `apply_review_gate(ctx, stage)` creates `PendingHumanAction` records.
3. Blocking actions prevent `node_stage_review(..., action="approve")` from moving to the next stage.
4. Actions can be resolved through:
   - `GET /sessions/{session_id}/actions`
   - `POST /sessions/{session_id}/actions/{action_id}/resolve`
   - `GET /sessions/{session_id}/audit-events`
5. The old `/sessions/{session_id}/flags/resolve` API is kept for compatibility and now also resolves actions derived from the same flag.

## Scope intentionally not included

- LangGraph interrupt/checkpoint adapter
- Schema-first JSON stage output
- EvidenceSource and SafetyFinding layers
- EvalCase system
