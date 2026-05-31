# Stage Transition Policy

Status: v0.6.0-alpha.8

This document describes the current deterministic phase-advancement rules implemented by the alpha.8 source. It replaces the older alpha.3 wording while preserving the same non-redesign scope.

Authoritative stage gate implementation:

```text
core/stage_readiness_service.py
```

Authoritative doc/test/core alignment matrix:

```text
docs/v0_6_0_alpha_8_core_code_alignment_contract.md
tests/ACCEPTANCE_TEST_ALIGNMENT_ALPHA8.md
tests/test_alpha8_doc_core_alignment_contract.py
```

Backward-compatible graph entry points:

```text
graph/transition_policy.py
graph/nodes.py
```

`graph.transition_policy.stage_can_continue()` delegates to the unified readiness service so graph, API, reports, and frontend explain the same blocker contract. Review-action resolution rules remain in `graph.transition_policy.evaluate_action_resolution()`.

## Global rule

Supporting modules may create signals, actions, reports, eval runs, and evidence records, but they must not advance stages directly. Stage advancement is allowed only when the authoritative gate for the current stage has no blockers.

Signals consumed by the gate include:

```text
EvidenceSource
SafetyFinding
EvalCase / EvalRun
PendingHumanAction
InterruptRecord
AuditEvent
ReportArtifact
stage_output_versions
stage_staleness
parser_errors
```

Before a stage can advance from review:

1. The current stage output must exist.
2. The current stage output version must not be stale because an upstream stage changed.
3. The current stage output version must have no pending blocking `PendingHumanAction`.
4. Rejected `approve`, `edit`, or `escalate` actions block advancement until the stage is revised, rerun, or rolled back.
5. `escalate` actions require explicit `reviewer_decision == "approve"`.
6. Parser errors block advancement until a structured edit provides the expected stage schema.
7. Open high/critical `SafetyFinding` records requiring human review block advancement.
8. Blockers are exposed through stage readiness, stage gate, stage resolution, reports, and the Review Workbench.

## Structured edit rule

The following source types require a complete structured stage payload when resolved through an edit action:

```text
parser
policy_gap
evidence_gap
eval_coverage
```

A note-only edit or `edited_text`-only payload does not remove these blockers. The payload must include `structured_output` or the expected stage schema key such as `failure_modes`, `workflow_nodes`, `test_cases`, or `trigger_methods`.

## Stage 1: Failure Mode + Evidence Gate

Stage 1 focuses on evidence-grounded failure-mode identification.

Additional readiness rules:

- High/critical `FailureMode` items must reference at least one `evidence_id`.
- A referenced high/critical evidence ID must exist in `ctx.evidence_sources`.
- Referenced high/critical evidence must be verified before advancement.
- Missing or unknown evidence IDs require a structured Stage 1 edit.
- Existing but unverified evidence is resolved through evidence verification.
- Low-credibility, unknown, or user/forum-derived evidence can create review actions and remains visible in reports.

## Stage 2: WorkflowNode + Oversight Policy Gate

Stage 2 turns risk findings into a human-supervised workflow.

Additional readiness rules:

- Every high/critical Stage 1 failure mode must be covered by at least one `WorkflowNode.failure_modes_addressed` entry.
- Nodes covering high/critical failure modes must include a `HumanOversightPolicy`.
- Missing coverage or policy creates a `policy_gap` blocker.
- `policy_gap` blockers require a structured Stage 2 edit, not a note-only approval.

## Stage 3: Stress Test + Eval Gate

Stage 3 validates the workflow through stress-test and eval signals.

Additional readiness rules:

- Every high-risk workflow node must have at least one Stage 3 `EvalCase`.
- Missing high-risk EvalCase coverage is a blocker in alpha.8, not only a warning.
- Failed high-risk `EvalCase` records block advancement until their review action is resolved.
- High-risk `EvalRun` records with `judge_result == "needs_review"` block advancement until reviewed.
- Failed high-risk `EvalRun` records block advancement until reviewed.
- `eval_coverage` edit actions require a complete structured Stage 3 payload.

## Stage 4: Trigger Method + Final Governance Gate

Stage 4 decides whether the workflow can be completed or exported as final.

Additional readiness rules:

- Trigger methods declaring `human_review_required=True` create blocking approval actions.
- Final governance wraps unresolved upstream hard blockers so completion cannot contradict earlier stage gates.
- Upstream blockers that require structured edits remain hard blockers at final governance time.
- Open high/critical safety findings remain visible as final governance blockers.
- Parser errors from any stage remain final governance blockers.
- Approval-overridable findings remain visible in their native stage; non-overridable hard blockers are enforced before final completion.

## Resolution operations

Stage blockers are mapped to concrete next operations through the source constants tested by `tests/test_alpha8_doc_core_alignment_contract.py`:

```text
core/stage_advancement_contract.py
core/stage_resolution_service.py
core/stage_operation_service.py
api/routers/stage.py
api/routers/oversight.py
api/routers/evidence.py
api/routers/safety.py
```

Executable stage operations are exposed under:

```text
POST /sessions/{session_id}/stages/{stage_id}/rerun
POST /sessions/{session_id}/stages/{stage_id}/revise
POST /sessions/{session_id}/stages/{stage_id}/rollback
POST /sessions/{session_id}/stages/{stage_id}/sync-review-actions
```

## Validation status

Full runtime validation remains deferred. The dependency-light alpha.8 contract subset has been validated separately from the full dependency stack. Full API startup, Streamlit startup, Docker validation, real LLM calls, Tavily calls, PostgreSQL integration, Redis integration, and end-to-end workflow validation still require the full project dependency environment.
