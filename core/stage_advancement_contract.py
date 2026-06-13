# core/stage_advancement_contract.py
"""Shared Stage Advancement Contract.

This module is intentionally declarative. It documents the blocker/action/
resolution contract used by stage_readiness_service, stage_resolution_service,
graph.nodes, reports, and the review workbench. It does not execute workflow
logic and must remain safe to import without external services.
"""

from __future__ import annotations

from typing import Final

STAGE_LIFECYCLES: Final[tuple[str, ...]] = (
    "not_started",
    "running",
    "review",
    "blocked",
    "ready_to_advance",
    "approved",
    "stale",
)

BLOCKER_TYPES: Final[tuple[str, ...]] = (
    "missing_stage_output",
    "stale_dependency",
    "pending_action",
    "rejected_action",
    "unresolved_escalation",
    "parser_error",
    "safety_finding",
    "evidence_gap",
    "policy_gap",
    "eval_failure",
    "redteam_coverage",
    "eval_regression",
    "trace_backfill_gap",
    "final_governance",
)

REQUIRED_RESOLUTIONS: Final[tuple[str, ...]] = (
    "run_stage",
    "rerun_stage",
    "resolve_action",
    "verify_evidence",
    "edit_stage_output",
    "revise_stage",
    "back_stage",
    "approve_escalation",
    "resolve_safety_finding",
    "create_eval_dataset_from_stage3",
    "add_eval_cases_to_dataset",
    "set_eval_baseline",
    "create_eval_experiment",
    "run_eval_experiment",
    "compare_eval_experiment",
    "generate_redteam_cases",
    "approve_redteam_case",
    "sync_redteam_eval_case",
    "create_redteam_dataset",
    "trace_to_eval_case",
    "create_trace_backfill_dataset",
)

# Source of truth for blocker -> expected resolution semantics.
STAGE_ADVANCEMENT_CONTRACT: Final[dict[str, dict[str, object]]] = {
    "missing_stage_output": {
        "required_resolution": "run_stage",
        "description": "The stage has not generated structured output yet.",
        "approval_override_allowed": False,
    },
    "stale_dependency": {
        "required_resolution": "rerun_stage",
        "description": "The stage output depends on an older upstream stage version.",
        "approval_override_allowed": False,
    },
    "pending_action": {
        "required_resolution": "resolve_action",
        "description": "A blocking PendingHumanAction for the current stage version is still pending.",
        "approval_override_allowed": False,
    },
    "rejected_action": {
        "required_resolution": "revise_stage",
        "description": "A critical action was rejected; the stage must be revised or rolled back.",
        "approval_override_allowed": False,
    },
    "unresolved_escalation": {
        "required_resolution": "approve_escalation",
        "description": "An escalation action must be explicitly approved before advancement.",
        "approval_override_allowed": False,
    },
    "parser_error": {
        "required_resolution": "edit_stage_output",
        "description": "Structured output parsing failed and must be corrected through edit/revise.",
        "approval_override_allowed": False,
    },
    "safety_finding": {
        "required_resolution": "resolve_safety_finding",
        "description": "High or critical safety findings must be resolved or explicitly approved.",
        "approval_override_allowed": True,
    },
    "evidence_gap": {
        "required_resolution": "verify_evidence",
        "description": "High-risk failure modes require valid evidence_id references and verified evidence sources; missing/unknown ids require structured edit, existing unverified ids require verify_evidence.",
        "approval_override_allowed": False,
    },
    "policy_gap": {
        "required_resolution": "edit_stage_output",
        "description": "High-risk workflow coverage or oversight-policy gaps must be edited/revised.",
        "approval_override_allowed": False,
    },
    "eval_failure": {
        "required_resolution": "resolve_action",
        "description": "Failed high-risk evals must be approved, edited, or rerun before advancement.",
        "approval_override_allowed": True,
    },
    "redteam_coverage": {
        "required_resolution": "generate_redteam_cases",
        "description": "High or critical risks require approved RedTeamCase coverage, synced EvalCase records, and a redteam_generated EvalDataset before Stage 3 advancement.",
        "approval_override_allowed": False,
    },
    "eval_regression": {
        "required_resolution": "create_eval_experiment",
        "description": "Gate-relevant EvalDatasets require cases, a baseline, a completed current EvalExperiment, and a non-regressing comparison before Stage 3 can advance. The concrete resolution is refined by eval_regression_policy per blocker status.",
        "approval_override_allowed": False,
    },
    "trace_backfill_gap": {
        "required_resolution": "trace_to_eval_case",
        "description": "Failed/parser/safety traces must be backfilled into EvalCase records and grouped into a production_trace EvalDataset before Stage 3 can advance.",
        "approval_override_allowed": False,
    },
    "final_governance": {
        "required_resolution": "resolve_safety_finding",
        "description": "Final report completion is blocked by unresolved governance items.",
        "approval_override_allowed": True,
    },
}

# Every stage blocker maps to an explicit user-facing operation instead of only a raw enum.
RESOLUTION_OPERATION_CONTRACT: Final[dict[str, dict[str, object]]] = {
    "run_stage": {
        "frontend_hint": "Run the current stage to generate structured output.",
        "api_hint": "Send user input through POST /chat/{session_id}.",
        "can_execute_via_api": False,
        "api_method": None,
        "api_path_template": None,
        "payload_hint": {},
    },
    "rerun_stage": {
        "frontend_hint": "Prepare this stale stage for rerun, then send revised input through chat to regenerate it.",
        "api_hint": "POST /sessions/{session_id}/stages/{stage_id}/rerun",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/stages/{stage_id}/rerun",
        "payload_hint": {"reason": "", "note": ""},
    },
    "resolve_action": {
        "frontend_hint": "Resolve the linked PendingHumanAction before advancing.",
        "api_hint": "POST /sessions/{session_id}/actions/{action_id}/resolve",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/actions/{action_id}/resolve",
        "payload_hint": {
            "decision": "approve | edit | reject | verify_evidence | dismissed",
            "note": "",
            "payload_after": {},
        },
    },
    "verify_evidence": {
        "frontend_hint": "Verify the evidence source itself; dismissing a human action does not remove evidence gates.",
        "api_hint": "POST /sessions/{session_id}/evidence/{evidence_id}/verify when the blocker source is an evidence id.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/evidence/{evidence_id}/verify",
        "payload_hint": {"note": ""},
    },
    "edit_stage_output": {
        "frontend_hint": "Edit the structured stage output or request a stage revision.",
        "api_hint": "Prefer POST /sessions/{session_id}/actions/{action_id}/resolve with decision=edit and payload_after.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/actions/{action_id}/resolve",
        "payload_hint": {
            "decision": "edit",
            "note": "",
            "payload_after": {"structured_output": {}, "edited_text": "optional explanation"},
        },
    },
    "revise_stage": {
        "frontend_hint": "Prepare the current stage for revision; regeneration still happens through the deterministic chat runner.",
        "api_hint": "POST /sessions/{session_id}/stages/{stage_id}/revise",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/stages/{stage_id}/revise",
        "payload_hint": {"reason": "", "note": ""},
    },
    "back_stage": {
        "frontend_hint": "Roll back to an earlier stage and supersede stale actions without executing the runtime.",
        "api_hint": "POST /sessions/{session_id}/stages/{stage_id}/rollback",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/stages/{stage_id}/rollback",
        "payload_hint": {"to_stage": 0, "reason": "", "note": "", "target_running": False},
    },
    "approve_escalation": {
        "frontend_hint": "Escalation actions require explicit approval by the responsible reviewer.",
        "api_hint": "POST /sessions/{session_id}/actions/{action_id}/resolve with decision=approve.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/actions/{action_id}/resolve",
        "payload_hint": {"decision": "approve", "note": "负责人已明确批准"},
    },
    "resolve_safety_finding": {
        "frontend_hint": "Resolve or dismiss the linked SafetyFinding and keep the audit record.",
        "api_hint": "POST /sessions/{session_id}/safety-findings/{finding_id}/resolve when the blocker source is a safety finding.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/safety-findings/{finding_id}/resolve",
        "payload_hint": {"status": "resolved | dismissed", "note": ""},
    },
    "create_eval_dataset_from_stage3": {
        "frontend_hint": "Create a gate-relevant EvalDataset from Stage 3 generated EvalCase records.",
        "api_hint": "POST /sessions/{session_id}/eval-datasets/from-stage3",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-datasets/from-stage3",
        "payload_hint": {
            "name": "Stage 3 generated dataset",
            "description": "",
            "version": "0.1",
            "owner": "system",
        },
    },
    "add_eval_cases_to_dataset": {
        "frontend_hint": "Add existing EvalCase ids to the linked EvalDataset before running regression checks.",
        "api_hint": "POST /sessions/{session_id}/eval-datasets/{dataset_id}/cases",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-datasets/{dataset_id}/cases",
        "payload_hint": {"eval_ids": []},
    },
    "set_eval_baseline": {
        "frontend_hint": "Set the linked EvalDataset baseline experiment before comparing the current run.",
        "api_hint": "POST /sessions/{session_id}/eval-datasets/{dataset_id}/baseline",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-datasets/{dataset_id}/baseline",
        "payload_hint": {"baseline_experiment_id": ""},
    },
    "create_eval_experiment": {
        "frontend_hint": "Create a current EvalExperiment for the linked EvalDataset, then run it.",
        "api_hint": "POST /sessions/{session_id}/eval-experiments",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-experiments",
        "payload_hint": {
            "dataset_id": "{source_id}",
            "name": "Current regression experiment",
            "run_mode": "dry_run",
            "run_config": {"runtime_validation": "deferred_by_instruction"},
        },
    },
    "run_eval_experiment": {
        "frontend_hint": "Run the linked EvalExperiment before advancing. If the blocker only references a dataset, create a current experiment for that dataset first.",
        "api_hint": "POST /sessions/{session_id}/eval-experiments/{experiment_id}/run when the blocker source is an EvalExperiment.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-experiments/{experiment_id}/run",
        "payload_hint": {"dry_run_only": True},
    },
    "compare_eval_experiment": {
        "frontend_hint": "Compare the current EvalExperiment with its baseline before advancing.",
        "api_hint": "POST /sessions/{session_id}/eval-experiments/{experiment_id}/comparison",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-experiments/{experiment_id}/comparison",
        "payload_hint": {"baseline_experiment_id": "optional"},
    },
    "generate_redteam_cases": {
        "frontend_hint": "Generate deterministic RedTeamCase drafts from current high-risk SafetyFinding, FailureMode, and WorkflowNode signals.",
        "api_hint": "POST /sessions/{session_id}/redteam/generate",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/redteam/generate",
        "payload_hint": {"stage": 3},
    },
    "approve_redteam_case": {
        "frontend_hint": "Approve the linked RedTeamCase before it can be synced into EvalCase.",
        "api_hint": "POST /sessions/{session_id}/redteam/cases/{case_id}/approve",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/redteam/cases/{case_id}/approve",
        "payload_hint": {"note": "reviewer approved redteam coverage"},
    },
    "sync_redteam_eval_case": {
        "frontend_hint": "Sync the approved RedTeamCase into an adversarial EvalCase.",
        "api_hint": "POST /sessions/{session_id}/redteam/cases/{case_id}/to-eval-case",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/redteam/cases/{case_id}/to-eval-case",
        "payload_hint": {},
    },
    "create_redteam_dataset": {
        "frontend_hint": "Create a redteam_generated EvalDataset from synced RedTeamCase EvalCases so Regression Gate can consume it.",
        "api_hint": "POST /sessions/{session_id}/redteam/datasets",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/redteam/datasets",
        "payload_hint": {"name": "Red Team generated dataset", "version": "0.1"},
    },
    "trace_to_eval_case": {
        "frontend_hint": "Convert the linked failed/parser/safety trace into a production regression EvalCase before advancing.",
        "api_hint": "POST /sessions/{session_id}/traces/{trace_id}/to-eval-case",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/traces/{trace_id}/to-eval-case",
        "payload_hint": {"expected_behavior": "optional", "target_node_id": "optional"},
    },
    "create_trace_backfill_dataset": {
        "frontend_hint": "Create a production_trace EvalDataset from trace-backfilled EvalCases so Regression Gate can consume it.",
        "api_hint": "POST /sessions/{session_id}/traces/to-eval-dataset",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/traces/to-eval-dataset",
        "payload_hint": {"name": "Trace backfill regression dataset", "version": "0.1"},
    },
}


def required_resolution_for(blocker_type: str) -> str:
    item = STAGE_ADVANCEMENT_CONTRACT.get(blocker_type)
    if not item:
        return "resolve_action"
    return str(item["required_resolution"])


def operation_contract_for(required_resolution: str) -> dict[str, object]:
    """Return the user-facing operation metadata for a required resolution."""
    return dict(
        RESOLUTION_OPERATION_CONTRACT.get(
            required_resolution, RESOLUTION_OPERATION_CONTRACT["resolve_action"]
        )
    )


def contract_summary() -> dict[str, object]:
    """Machine-readable contract snapshot for docs, reports, and API diagnostics."""
    return {
        "stage_lifecycles": STAGE_LIFECYCLES,
        "blocker_types": BLOCKER_TYPES,
        "required_resolutions": REQUIRED_RESOLUTIONS,
        "stage_advancement_contract": STAGE_ADVANCEMENT_CONTRACT,
        "resolution_operation_contract": RESOLUTION_OPERATION_CONTRACT,
    }
