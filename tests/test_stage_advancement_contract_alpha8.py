# tests/test_stage_advancement_contract_alpha8.py
"""Contract tests for the v0.6.0-alpha.8 stage advancement closure layer."""

from __future__ import annotations

from core.models import (
    EvalCase,
    EvalRun,
    FailureMode,
    HumanActionStatus,
    PendingHumanAction,
    ProjectContext,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    WorkflowNode,
)
from core.stage_advancement_contract import RESOLUTION_OPERATION_CONTRACT
from core.stage_readiness_service import evaluate_stage_gate
from core.stage_resolution_service import build_stage_resolution_operations


def test_resolution_contract_covers_alpha8_required_resolutions() -> None:
    required = {
        "run_stage",
        "rerun_stage",
        "resolve_action",
        "verify_evidence",
        "edit_stage_output",
        "revise_stage",
        "back_stage",
        "approve_escalation",
        "resolve_safety_finding",
    }
    assert required.issubset(set(RESOLUTION_OPERATION_CONTRACT))


def test_alpha8_stage_operation_contracts_bind_stage_id_paths() -> None:
    for resolution in {"rerun_stage", "revise_stage", "back_stage"}:
        contract = RESOLUTION_OPERATION_CONTRACT[resolution]
        assert contract["can_execute_via_api"] is True
        assert contract["api_method"] == "POST"
        assert "{stage_id}" in contract["api_path_template"]

    assert RESOLUTION_OPERATION_CONTRACT["rerun_stage"]["api_path_template"] == (
        "/sessions/{session_id}/stages/{stage_id}/rerun"
    )
    assert RESOLUTION_OPERATION_CONTRACT["revise_stage"]["api_path_template"] == (
        "/sessions/{session_id}/stages/{stage_id}/revise"
    )
    assert RESOLUTION_OPERATION_CONTRACT["back_stage"]["api_path_template"] == (
        "/sessions/{session_id}/stages/{stage_id}/rollback"
    )


def test_missing_stage_output_maps_to_run_stage_operation() -> None:
    ctx = ProjectContext(current_state=SessionState.S1_REVIEW)
    gate = evaluate_stage_gate(ctx, 1)
    assert not gate.can_continue
    assert gate.blockers[0].blocker_type == "missing_stage_output"
    operations = build_stage_resolution_operations(ctx, 1)
    assert operations[0].required_resolution == "run_stage"


def test_stale_dependency_maps_to_executable_rerun_stage_operation() -> None:
    ctx = ProjectContext(current_state=SessionState.S2_REVIEW)
    ctx.stage_2_output = Stage2Output()
    ctx.stage_output_versions["stage_2"] = 1
    ctx.stage_staleness["stage_2"] = {"stale": True, "reason": "stage_1 changed"}

    operations = build_stage_resolution_operations(ctx, 2)

    rerun = next(op for op in operations if op.required_resolution == "rerun_stage")
    assert rerun.can_execute_via_api is True
    assert rerun.api_path == f"/sessions/{ctx.session_id}/stages/2/rerun"


def test_pending_action_maps_to_resolve_action_operation() -> None:
    ctx = ProjectContext(current_state=SessionState.S1_REVIEW)
    ctx.stage_output_versions["stage_1"] = 1
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            source_type="failure_mode",
            source_id="FM-1",
            action_type="approve",
            title="Review high-risk failure mode",
            description="Must be approved before advancing.",
            risk_level="high",
            blocking=True,
            stage_output_version=1,
        )
    )
    operations = build_stage_resolution_operations(ctx, 1)
    assert any(op.required_resolution == "resolve_action" for op in operations)
    assert any(op.api_path and "/actions/" in op.api_path for op in operations)


def test_resolved_rejected_action_maps_to_revise_stage_operation() -> None:
    ctx = ProjectContext(current_state=SessionState.S1_REVIEW)
    ctx.stage_1_output = Stage1Output()
    ctx.stage_output_versions["stage_1"] = 1
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            source_type="parser",
            source_id="stage_1",
            action_type="edit",
            title="Fix parser error",
            description="Edit structured output.",
            risk_level="high",
            blocking=True,
            stage_output_version=1,
            status=HumanActionStatus.RESOLVED.value,
            reviewer_decision="reject",
        )
    )
    operations = build_stage_resolution_operations(ctx, 1)
    revise = next(op for op in operations if op.required_resolution == "revise_stage")
    assert revise.can_execute_via_api is True
    assert revise.api_path == f"/sessions/{ctx.session_id}/stages/1/revise"


def test_stage3_high_risk_node_without_eval_case_blocks_as_eval_coverage() -> None:
    ctx = ProjectContext(current_state=SessionState.S3_REVIEW)
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-HIGH",
                category="hallucination",
                description="must be covered",
                severity="high",
            )
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N1",
                stage_name="draft",
                model_assigned="deepseek-chat",
                human_action="review",
                check_criteria="must cite evidence",
                failure_modes_addressed=["FM-HIGH"],
                prompt_template="Draft with citations only.",
            )
        ]
    )
    ctx.stage_3_output = Stage3Output()
    ctx.stage_output_versions["stage_3"] = 1

    operations = build_stage_resolution_operations(ctx, 3)

    coverage = next(op for op in operations if op.source_type == "eval_coverage")
    assert coverage.required_resolution == "edit_stage_output"
    assert coverage.hard_blocker is True
    assert coverage.metadata["blocker_metadata"]["requires_structured_output"] is True


def test_stage3_high_risk_eval_run_needs_review_blocks_with_resolve_action() -> None:
    ctx = ProjectContext(current_state=SessionState.S3_REVIEW)
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-HIGH",
                category="hallucination",
                description="must be reviewed",
                severity="high",
            )
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N1",
                stage_name="draft",
                model_assigned="deepseek-chat",
                human_action="review",
                check_criteria="must cite evidence",
                failure_modes_addressed=["FM-HIGH"],
                prompt_template="Draft with citations only.",
            )
        ]
    )
    ctx.stage_3_output = Stage3Output()
    case = EvalCase(
        session_id=ctx.session_id,
        target_node_id="N1",
        covered_failure_mode_ids=["FM-HIGH"],
        input_payload="test input",
        expected_behavior="needs safe output",
    )
    ctx.eval_cases.append(case)
    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        target_node_id="N1",
        covered_failure_mode_ids=["FM-HIGH"],
        run_mode="dry_run",
        input_payload="test input",
        expected_behavior="needs safe output",
        judge_result="needs_review",
        judge_reason="Dry run validates eval plumbing but does not execute a target node.",
        status="completed",
    )
    ctx.eval_runs.append(run)
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=3,
            source_type="eval_run",
            source_id=run.run_id,
            action_type="edit",
            title="Review required eval run",
            description="EvalRun requires human review.",
            risk_level="high",
            blocking=True,
            stage_output_version=1,
        )
    )

    gate = evaluate_stage_gate(ctx, 3)
    eval_failure_blocker = next(
        blocker
        for blocker in gate.blockers
        if blocker.source_type == "eval_run" and blocker.blocker_type == "eval_failure"
    )
    assert eval_failure_blocker.required_resolution == "resolve_action"
    assert eval_failure_blocker.can_be_overridden_by_approval is True

    operations = build_stage_resolution_operations(ctx, 3)

    # StageResolutionOperation de-duplicates multiple blockers that resolve
    # through the same concrete PendingHumanAction. The executable operation
    # should therefore point to the pending eval_run action.
    pending_action_op = next(
        op
        for op in operations
        if op.source_type == "eval_run" and op.blocker_type == "pending_action"
    )
    assert pending_action_op.required_resolution == "resolve_action"
    assert pending_action_op.hard_blocker is True
    assert pending_action_op.can_execute_via_api is True
    assert pending_action_op.api_path and "/actions/" in pending_action_op.api_path
