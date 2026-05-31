# Stage Advancement Contract Matrix — alpha.10 source-freeze check

Generated: 2026-05-29  
Package stage: `v0.8.0-alpha.10-source-freeze-check`  
Runtime validation: `deferred_by_instruction`

This document is generated from the real source file:

```text
core/stage_advancement_contract.py
```

It is a source-level contract matrix only. It does not run pytest, import smoke checks,
FastAPI, Streamlit, Docker, LLM calls, Search calls, PostgreSQL, Redis, or E2E flows.

## Contract Closure Rule

Every current gate blocker must map through this chain:

```text
GateRule -> StageBlocker.blocker_type -> required_resolution -> StageResolutionOperation -> optional API path -> StageOperationEnvelope refresh
```

## Blocker to resolution matrix

| Gate Rule | Blocker Type | Required Resolution | API Path Template | API-capable | Approval Override | Frontend Hint |
|---|---|---|---|---:|---:|---|
| missing_output | missing_stage_output | run_stage | chat/runtime or non-API operation | no | no | Run the current stage to generate structured output. |
| stale_dependency | stale_dependency | rerun_stage | /sessions/{session_id}/stages/{stage_id}/rerun | yes | no | Prepare this stale stage for rerun, then send revised input through chat to regenerate it. |
| action_state | pending_action | resolve_action | /sessions/{session_id}/actions/{action_id}/resolve | yes | no | Resolve the linked PendingHumanAction before advancing. |
| action_state | rejected_action | revise_stage | /sessions/{session_id}/stages/{stage_id}/revise | yes | no | Prepare the current stage for revision; regeneration still happens through the deterministic chat runner. |
| action_state | unresolved_escalation | approve_escalation | /sessions/{session_id}/actions/{action_id}/resolve | yes | no | Escalation actions require explicit approval by the responsible reviewer. |
| parser_error | parser_error | edit_stage_output | /sessions/{session_id}/actions/{action_id}/resolve | yes | no | Edit the structured stage output or request a stage revision. |
| safety_finding | safety_finding | resolve_safety_finding | /sessions/{session_id}/safety-findings/{finding_id}/resolve | yes | yes | Resolve or dismiss the linked SafetyFinding and keep the audit record. |
| stage1_evidence_gap | evidence_gap | verify_evidence | /sessions/{session_id}/evidence/{evidence_id}/verify | yes | no | Verify the evidence source itself; dismissing a human action does not remove evidence gates. |
| stage2_policy_gap | policy_gap | edit_stage_output | /sessions/{session_id}/actions/{action_id}/resolve | yes | no | Edit the structured stage output or request a stage revision. |
| stage3_eval_failure | eval_failure | resolve_action | /sessions/{session_id}/actions/{action_id}/resolve | yes | yes | Resolve the linked PendingHumanAction before advancing. |
| redteam_coverage | redteam_coverage | generate_redteam_cases | /sessions/{session_id}/redteam/generate | yes | no | Generate deterministic RedTeamCase drafts from current high-risk SafetyFinding, FailureMode, and WorkflowNode signals. |
| eval_regression | eval_regression | create_eval_experiment | /sessions/{session_id}/eval-experiments | yes | no | Create a current EvalExperiment for the linked EvalDataset, then run it. |
| trace_backfill_gap | trace_backfill_gap | trace_to_eval_case | /sessions/{session_id}/traces/{trace_id}/to-eval-case | yes | no | Convert the linked failed/parser/safety trace into a production regression EvalCase before advancing. |
| stage4_final_governance | final_governance | resolve_safety_finding | /sessions/{session_id}/safety-findings/{finding_id}/resolve | yes | yes | Resolve or dismiss the linked SafetyFinding and keep the audit record. |

## Required resolution operation matrix

| Required Resolution | API Path Template | API-capable | Payload Hint |
|---|---|---:|---|
| run_stage | none | no | {} |
| rerun_stage | /sessions/{session_id}/stages/{stage_id}/rerun | yes | {'reason': '', 'note': ''} |
| resolve_action | /sessions/{session_id}/actions/{action_id}/resolve | yes | {'decision': 'approve \| edit \| reject \| verify_evidence \| dismissed', 'note': '', 'payload_after': {}} |
| verify_evidence | /sessions/{session_id}/evidence/{evidence_id}/verify | yes | {'note': ''} |
| edit_stage_output | /sessions/{session_id}/actions/{action_id}/resolve | yes | {'decision': 'edit', 'note': '', 'payload_after': {'structured_output': {}, 'edited_text': 'optional explanation'}} |
| revise_stage | /sessions/{session_id}/stages/{stage_id}/revise | yes | {'reason': '', 'note': ''} |
| back_stage | /sessions/{session_id}/stages/{stage_id}/rollback | yes | {'to_stage': 0, 'reason': '', 'note': '', 'target_running': False} |
| approve_escalation | /sessions/{session_id}/actions/{action_id}/resolve | yes | {'decision': 'approve', 'note': '负责人已明确批准'} |
| resolve_safety_finding | /sessions/{session_id}/safety-findings/{finding_id}/resolve | yes | {'status': 'resolved \| dismissed', 'note': ''} |
| create_eval_dataset_from_stage3 | /sessions/{session_id}/eval-datasets/from-stage3 | yes | {'name': 'Stage 3 generated dataset', 'description': '', 'version': '0.1', 'owner': 'system'} |
| add_eval_cases_to_dataset | /sessions/{session_id}/eval-datasets/{dataset_id}/cases | yes | {'eval_ids': []} |
| set_eval_baseline | /sessions/{session_id}/eval-datasets/{dataset_id}/baseline | yes | {'baseline_experiment_id': ''} |
| create_eval_experiment | /sessions/{session_id}/eval-experiments | yes | {'dataset_id': '{source_id}', 'name': 'Current regression experiment', 'run_mode': 'dry_run', 'run_config': {'runtime_validation': 'deferred_by_instruction'}} |
| run_eval_experiment | /sessions/{session_id}/eval-experiments/{experiment_id}/run | yes | {'dry_run_only': True} |
| compare_eval_experiment | /sessions/{session_id}/eval-experiments/{experiment_id}/comparison | yes | {'baseline_experiment_id': 'optional'} |
| generate_redteam_cases | /sessions/{session_id}/redteam/generate | yes | {'stage': 3} |
| approve_redteam_case | /sessions/{session_id}/redteam/cases/{case_id}/approve | yes | {'note': 'reviewer approved redteam coverage'} |
| sync_redteam_eval_case | /sessions/{session_id}/redteam/cases/{case_id}/to-eval-case | yes | {} |
| create_redteam_dataset | /sessions/{session_id}/redteam/datasets | yes | {'name': 'Red Team generated dataset', 'version': '0.1'} |
| trace_to_eval_case | /sessions/{session_id}/traces/{trace_id}/to-eval-case | yes | {'expected_behavior': 'optional', 'target_node_id': 'optional'} |
| create_trace_backfill_dataset | /sessions/{session_id}/traces/to-eval-dataset | yes | {'name': 'Trace backfill regression dataset', 'version': '0.1'} |

## Source-freeze conclusion

Source-level review confirms that alpha.10 has a single declarative contract file
for blocker and resolution semantics. The next validation pass must still prove
that every concrete runtime blocker produced by each GateRule carries a source id
that can bind to the corresponding API path when `can_execute_via_api=true`.

## Out of scope

- No v0.9 Workspace / Project / RBAC implementation.
- No Claim-Evidence Graph implementation.
- No Report Center approval / publish workflow.
- No runtime test execution.
