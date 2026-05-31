# Stage Advancement Contract v0.6.0-alpha.6

## Purpose

`v0.6.0-alpha.6` closes the stage-advancement loop introduced in alpha.5.

Alpha.5 answers:

```text
Why is a stage blocked?
```

Alpha.6 adds:

```text
What exact operation should the user/API/report perform next?
```

This patch does not redesign the project. It preserves:

```text
StageExecutor
→ ReviewGate
→ PendingHumanAction
→ StageBlocker / StageGateResult
→ TransitionPolicy
→ StageReadiness
→ next stage / stale / complete
```

and adds:

```text
StageBlocker
→ RequiredResolution
→ StageResolutionOperation
→ API / frontend / report hints
```

## Source of Truth

The authoritative stage decision remains:

```text
core.stage_readiness_service.evaluate_stage_gate(ctx, stage)
```

The concrete user operation layer is:

```text
core.stage_resolution_service.build_stage_resolution_operations(ctx, stage)
```

`StageReadiness` should continue to be used for display and reporting. `StageResolutionOperation` should be used when the UI or API needs to tell the user what to do next.

## Blocker to Resolution Contract

The existing blocker types remain unchanged:

```text
missing_stage_output
stale_dependency
pending_action
rejected_action
unresolved_escalation
parser_error
safety_finding
evidence_gap
policy_gap
eval_failure
final_governance
```

The existing required resolutions remain unchanged:

```text
run_stage
rerun_stage
resolve_action
verify_evidence
edit_stage_output
revise_stage
back_stage
approve_escalation
resolve_safety_finding
```

Alpha.6 adds `RESOLUTION_OPERATION_CONTRACT`, which maps every required resolution to:

```text
frontend_hint
api_hint
can_execute_via_api
api_method
api_path_template
payload_hint
```

## API Additions

```text
GET /sessions/{session_id}/stage-gate/{stage_id}
GET /sessions/{session_id}/stage-resolution
GET /sessions/{session_id}/stage-resolution/{stage_id}
```

These endpoints are read-only. They do not mutate session state, run a stage, resolve an action, verify evidence, or close safety findings.

## Report Additions

`build_report_dict(ctx)` now includes:

```text
stage_resolution_summary
next_required_operation
```

Markdown export includes a `Stage Resolution Operations` section before the main project overview.

## Frontend Additions

The Streamlit Review Workbench now shows operation cards under the Stage Gate panel. These cards are derived from `StageResolutionOperation`, not from local frontend rules.

Each operation card can show:

```text
required_resolution
blocker_type
hard / overridable
frontend_hint
action_id
api_path
payload_hint
```

## Version and Staleness Rules

No existing alpha.5 version semantics are replaced.

The rules remain:

| Operation | Version effect | Downstream effect |
|---|---|---|
| stage executor regenerate | bump current stage version | mark downstream stale |
| edit action with payload_after | bump current stage version | mark downstream stale |
| revise stage | prepare current stage for regeneration | stale downstream |
| rollback stage | return to earlier stage | stale later stages |

Alpha.6 adds `StageMutationResult` as a non-breaking summary model for future API responses. Existing functions still return `ProjectContext`.

## Deferred Validation

By instruction, this patch does not run:

```text
pytest
API startup
Streamlit startup
Docker validation
runtime workflow validation
```

Static test files and scenario files are included for later unified validation.
