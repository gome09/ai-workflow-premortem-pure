# Action Resolution Contract — v0.7-alpha.3

## Purpose

`PendingHumanAction` is the workflow's human-governance contract. Stage
advancement must depend on explicit action-resolution outcomes rather than
informal UI state.

## Result statuses

| Current action state | Request | Result status | Stage advancement meaning |
| --- | --- | --- | --- |
| pending | approve/edit/reject/verify/escalate | resolved | A real mutation or governance decision was accepted. Gate may be recalculated. |
| resolved | same idempotency_key | idempotent_replay | No new side effect. Return the previous resolution result. |
| resolved/cancelled/superseded/stale | different or missing idempotency_key | not_pending | Do not advance; caller must refresh action queue. |
| pending but old stage_output_version | any | stale | Do not apply. Caller must refresh/re-run/revise stage. |
| pending but expected_before_hash mismatch | any | conflict | Do not apply. Caller must reload current action payload. |
| pending but target_object_path cannot resolve | any | conflict | Do not apply. Current ProjectContext does not match the action contract. |
| edit with invalid structured payload | edit | validation_failed | Do not mutate reviewed_outputs or stage output. |
| missing action_id | any | not_found | Caller must refresh action queue. |

## Hash fields

`ActionResolutionResult` exposes three hash concepts:

- `before_hash`: hash of the action object before processing.
- `after_hash`: hash of the action object after processing when available.
- `action_hash`: preferred current action hash alias for API/UI clients.
- `payload_before_hash`: hash of `action.payload_before`.
- `payload_after_hash`: hash of the accepted `payload_after`, if any.

API/UI clients should send `expected_before_hash` using either `before_hash`
or `payload_before_hash`. A mismatch returns `conflict`.

## Audit and logs

- `action_resolution_logs` records every processing attempt, including stale,
  conflict, validation failure, and resolved outcomes.
- `audit_events` should represent business-state mutations.
- `idempotent_replay` must not create duplicate audit events.
- Stage rerun/revision/rollback must mark obsolete pending/rejected actions
  as `superseded` and record `superseded_by`.

## Stage advancement rule

Stage advancement must be calculated by `GateEngine` after action resolution.
A resolved action does not itself guarantee advancement; it only removes or
modifies one blocker source. The gate result remains authoritative.
