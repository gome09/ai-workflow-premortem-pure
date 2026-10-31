# core/oversight_service.py
"""Backward-compatible import surface for human-action governance.

The implementation moved to :mod:`core.governance` in Milestone 2. Existing
callers keep importing from this module.
"""

from __future__ import annotations

from core.governance.action_factory import (
    _high_risk_node_ids_for_eval,
    _risk_for_failure_mode_ids,
    create_actions_from_eval_failures,
    create_actions_from_eval_regression,
    create_actions_from_evidence_gaps,
    create_actions_from_failure_modes,
    create_actions_from_flags,
    create_actions_from_parser_errors,
    create_actions_from_policy_gaps,
    create_actions_from_redteam_gaps,
    create_actions_from_safety_findings,
    create_actions_from_stage3_result,
    create_actions_from_trace_backfill_gaps,
    create_actions_from_trigger_methods,
    create_actions_from_workflow_policies,
    create_review_actions_for_stage,
)
from core.governance.action_resolution import (
    _ACTION_SOURCE_LABEL,
    _RISK_LABEL,
    cancel_pending_actions_for_stage,
    format_pending_actions_for_review,
    resolve_action,
    resolve_action_with_result,
    resolve_actions_for_evidence,
    resolve_actions_for_flag,
    supersede_actions_for_stage,
)
from core.governance.action_state import (
    EVIDENCE_POLICY,
    _action_resolution_log_exists,
    _append_action_resolution_log,
    _has_action,
    _latest_action_resolution_log,
    _model_payload,
    _stable_hash,
    _target_object_exists,
    add_action_if_missing,
    bump_stage_output_version,
    current_stage_output_version,
)

__all__ = [
    "EVIDENCE_POLICY",
    "_model_payload",
    "_stable_hash",
    "_action_resolution_log_exists",
    "_append_action_resolution_log",
    "_latest_action_resolution_log",
    "_target_object_exists",
    "current_stage_output_version",
    "bump_stage_output_version",
    "_has_action",
    "add_action_if_missing",
    "create_actions_from_flags",
    "create_actions_from_failure_modes",
    "create_actions_from_evidence_gaps",
    "create_actions_from_workflow_policies",
    "create_actions_from_policy_gaps",
    "create_actions_from_stage3_result",
    "create_actions_from_trace_backfill_gaps",
    "create_actions_from_eval_regression",
    "_risk_for_failure_mode_ids",
    "_high_risk_node_ids_for_eval",
    "create_actions_from_eval_failures",
    "create_actions_from_trigger_methods",
    "create_actions_from_safety_findings",
    "create_actions_from_redteam_gaps",
    "create_actions_from_parser_errors",
    "create_review_actions_for_stage",
    "resolve_action",
    "resolve_action_with_result",
    "resolve_actions_for_flag",
    "resolve_actions_for_evidence",
    "supersede_actions_for_stage",
    "cancel_pending_actions_for_stage",
    "_RISK_LABEL",
    "_ACTION_SOURCE_LABEL",
    "format_pending_actions_for_review",
]
