# v0.5.2-alpha Stabilization Patch

This patch is based on the real uploaded `v0.5.1-alpha closeout` source package.

## Implemented

- Fixed manual `EvalRun` lifecycle by setting `status="completed"` and `completed_at`.
- Aligned package/version metadata to `0.5.2-alpha`.
- Added `STAGE_OUTPUT_MODE` and `WORKFLOW_EXECUTION_MODE` to `.env.example`.
- Added JSON-safe `AuditEvent.before_snapshot` and `AuditEvent.after_snapshot`.
- Persisted audit snapshots in the `audit_events` table.
- Synced safety finding `resolution_note` and `resolved_at` when resolved through a `PendingHumanAction`.
- Added persistent `interrupt_records` storage as preparation for v0.6 interrupt/checkpoint work.
- Added `scripts/version_check.py` for version consistency checks.

## Boundary

`WORKFLOW_EXECUTION_MODE=langgraph_interrupt` remains adapter-only in this patch. The stable production path remains `single_step`.

## Test note

Per request, pytest was not executed during patch generation. `python -m compileall -q .` was executed.
