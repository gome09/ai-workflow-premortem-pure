# core/stage_advancement_decision.py
"""Unified stage-advancement decision contract.

This module does not redesign the workflow and does not execute runtime
validation. It gives graph/API/frontend/report code one authoritative view of
whether a stage can advance, which blockers prevent advancement, which
resolution operations should be performed next, and how mutating operations
should return a refreshed advancement decision envelope.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.stage_readiness_service import StageGateResult, StageLifecycle
from core.stage_resolution_service import StageResolutionOperation

DecisionSource = Literal[
    "stage_gate",
    "graph_review",
    "api_advance",
    "chat_message_processed",
    "materials_added",
    "action_resolution",
    "flag_resolution",
    "evidence_resolution",
    "safety_resolution",
    "stage_rerun",
    "stage_revision",
    "stage_rollback",
    "sync_review_actions",
    "eval_cases_run",
    "eval_case_scored",
    "eval_dataset_created",
    "eval_dataset_updated",
    "eval_baseline_set",
    "eval_experiment_created",
    "eval_experiment_run",
    "eval_experiment_compared",
    "eval_run_calibrated",
    "redteam_cases_generated",
    "redteam_case_created",
    "redteam_case_approved",
    "redteam_case_rejected",
    "redteam_case_synced",
    "redteam_dataset_created",
    "trace_backfilled_to_eval_case",
    "trace_backfill_dataset_created",
    "report_artifact_created",
    "system",
]


class StageAdvancementDecision(BaseModel):
    """Single read model for stage advancement.

    `can_advance` means the gate allows advancement. `advanced` means a caller
    explicitly requested advancement and the current_state was actually mutated.
    GET-style callers should normally see `advanced=False`.
    """

    session_id: str
    stage_id: int
    stage_output_version: int
    current_state: str
    stage_lifecycle: StageLifecycle = "not_started"

    can_advance: bool
    advanced: bool = False
    next_state: str | None = None

    gate_result: StageGateResult
    required_operations: list[StageResolutionOperation] = Field(default_factory=list)
    blocking_action_ids: list[str] = Field(default_factory=list)
    stale_stage_keys: list[str] = Field(default_factory=list)

    decision_reason: str
    decision_source: DecisionSource = "stage_gate"
    rules_evaluated: list[str] = Field(default_factory=list)

    hard_blockers_count: int = 0
    overridable_blockers_count: int = 0
    executable_operations_count: int = 0

    trace_id: str | None = None
    runtime_validation: str = "deferred_by_instruction"
    metadata: dict = Field(default_factory=dict)


class StageOperationEnvelope(BaseModel):
    """Standard response envelope for mutating operations that affect stage gates.

    The payload intentionally preserves the domain result while adding the
    authoritative StageAdvancementDecision and the next concrete operation. API
    routers may merge the domain result into the top level for backward
    compatibility. This envelope is the canonical stage-operation contract.
    """

    session_id: str
    operation: str
    result: Any = None
    result_type: str = "unknown"
    stage_id: int
    stage_advancement_decision: StageAdvancementDecision
    next_required_operation: dict[str, Any] | None = None
    runtime_validation: str = "deferred_by_instruction"
    metadata: dict[str, Any] = Field(default_factory=dict)
