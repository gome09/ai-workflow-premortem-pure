# v0.6.0-alpha.5 Stage Advancement Contract Hardening

This patch is an incremental hardening layer over the real `v0.6.0-alpha.4`
source. It does not redesign the project and does not change the product
positioning.

## Scope

The alpha.5 scope is limited to stage advancement:

```text
StageExecutor
→ ReviewGate
→ PendingHumanAction
→ StageBlocker / StageGateResult
→ TransitionPolicy
→ StageReadiness
→ next stage / complete
```

Evidence, Safety, Eval, Report, and Interrupt records remain supporting inputs
to stage readiness. They do not directly own stage transitions.

## New contract elements

### Blocker types

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

### Required resolutions

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

## Stage lifecycle

Readiness now includes:

```text
not_started
running
review
blocked
ready_to_advance
approved
stale
```

`missing_stage_output` makes it explicit that no stage can advance before it has
generated structured output. `stale_dependency` makes downstream stages stop
after an upstream edit, revise, rollback, or regeneration.

## Version lineage

`ProjectContext` now records:

```python
stage_dependency_versions: dict[str, dict[str, int]]
stage_staleness: dict[str, dict]
```

Example:

```json
{
  "stage_3": {
    "stage_1": 2,
    "stage_2": 4
  }
}
```

If Stage 2 is later edited to version 5, Stage 3 becomes stale and cannot
advance until rerun.

## Edit / revise / rollback

- Structured edit bumps the current stage output version.
- The edited stage records fresh dependency versions.
- Downstream stages are marked stale if they have existing outputs, actions,
  parser errors, or dependency metadata.
- Pending/rejected downstream actions are superseded so old action IDs do not
  block the new lineage.
- Existing downstream outputs are preserved for auditability instead of being
  destructively deleted.

## Validation status

No pytest, service startup, Docker validation, or runtime smoke test was run for
this patch. Validation is intentionally deferred until the feature boundary is
frozen.
