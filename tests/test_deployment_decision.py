# tests/test_deployment_decision.py
"""WS-7: Deployment decision engine tests.

Validates ``generate_deployment_decision`` deterministic logic:
- critical open risk or failed evals → no_go
- high open risk / blocking actions / expert review pending → conditional_go
- all clear → pilot_only (demo conservative default)
"""

from __future__ import annotations

from core.deployment_decision_engine import (
    apply_deployment_decision,
    generate_deployment_decision,
)
from core.models import (
    EvalRun,
    FailureMode,
    PendingHumanAction,
    ProjectContext,
    SafetyFinding,
    Stage1Output,
    Stage2Output,
    Stage4Output,
    WorkflowNode,
)


def _base_ctx() -> ProjectContext:
    ctx = ProjectContext()
    ctx.session_id = "sess-deploy"
    ctx.tenant_id = "tenant-deploy"
    return ctx


def _finding(
    *,
    severity: str = "high",
    status: str = "open",
    finding_id: str = "SAFE-1",
) -> SafetyFinding:
    return SafetyFinding(
        finding_id=finding_id,
        session_id="sess-deploy",
        stage_id=3,
        risk_type="prompt_injection",
        severity=severity,  # type: ignore[arg-type]
        location="stage_3/test",
        description="test finding",
        recommended_action="resolve",
        status=status,  # type: ignore[arg-type]
    )


def _failed_eval_run(run_id: str = "RUN-FAIL") -> EvalRun:
    return EvalRun(
        run_id=run_id,
        session_id="sess-deploy",
        eval_id="EVAL-1",
        input_payload="...",
        expected_behavior="...",
        judge_result="failed",
    )


# ─────────────────────────────────────────────
# 1. Critical open risk → no_go
# ─────────────────────────────────────────────


def test_critical_open_risk_produces_no_go():
    ctx = _base_ctx()
    ctx.safety_findings.append(_finding(severity="critical", status="open"))

    decision = generate_deployment_decision(ctx)
    assert decision.decision == "no_go"
    assert decision.decision_scope == "deployment_paused"
    assert decision.is_demo_recommendation is True
    assert decision.rollback_conditions, "no_go must include rollback conditions"
    assert decision.prohibited_uses, "no_go must list prohibited uses"


def test_critical_resolved_risk_does_not_force_no_go():
    """A resolved critical finding must NOT trigger no_go by itself."""
    ctx = _base_ctx()
    ctx.safety_findings.append(_finding(severity="critical", status="resolved"))

    decision = generate_deployment_decision(ctx)
    assert decision.decision != "no_go", (
        f"resolved critical should not force no_go, got {decision.decision}"
    )


# ─────────────────────────────────────────────
# 2. High open risk → conditional_go (or no_go)
# ─────────────────────────────────────────────


def test_high_open_risk_produces_conditional_go():
    ctx = _base_ctx()
    ctx.safety_findings.append(_finding(severity="high", status="open"))

    decision = generate_deployment_decision(ctx)
    assert decision.decision in {"conditional_go", "no_go"}
    assert decision.decision == "conditional_go", (
        f"high open risk without critical/failed evals should be conditional_go, "
        f"got {decision.decision}"
    )
    assert decision.required_conditions, "conditional_go must have non-empty required_conditions"


# ─────────────────────────────────────────────
# 3. Failed eval → no_go
# ─────────────────────────────────────────────


def test_failed_eval_produces_no_go():
    ctx = _base_ctx()
    ctx.eval_runs.append(_failed_eval_run())

    decision = generate_deployment_decision(ctx)
    assert decision.decision in {"no_go", "conditional_go"}
    assert decision.decision == "no_go", (
        f"failed eval should produce no_go, got {decision.decision}"
    )


# ─────────────────────────────────────────────
# 4. All clear → pilot_only
# ─────────────────────────────────────────────


def test_all_clear_produces_pilot_only():
    ctx = _base_ctx()
    # No safety_findings, no failed eval_runs, no pending_actions

    decision = generate_deployment_decision(ctx)
    assert decision.decision in {"pilot_only", "conditional_go", "go"}
    assert decision.decision == "pilot_only", (
        f"all clear should produce pilot_only, got {decision.decision}"
    )
    assert decision.rollback_conditions, "pilot_only must have non-empty rollback_conditions"
    assert decision.required_conditions, "pilot_only must have non-empty required_conditions"


# ─────────────────────────────────────────────
# 5. conditional_go has required_conditions; pilot_only has rollback_conditions
# ─────────────────────────────────────────────


def test_conditional_go_required_conditions_non_empty():
    ctx = _base_ctx()
    ctx.safety_findings.append(_finding(severity="high", status="open"))

    decision = generate_deployment_decision(ctx)
    assert decision.decision == "conditional_go"
    assert len(decision.required_conditions) > 0
    # Each condition should be a non-empty string
    assert all(isinstance(c, str) and c for c in decision.required_conditions)


def test_pilot_only_rollback_conditions_non_empty():
    ctx = _base_ctx()

    decision = generate_deployment_decision(ctx)
    assert decision.decision == "pilot_only"
    assert len(decision.rollback_conditions) > 0
    assert all(isinstance(c, str) and c for c in decision.rollback_conditions)


# ─────────────────────────────────────────────
# 6. is_demo_recommendation is always True
# ─────────────────────────────────────────────


def test_is_demo_recommendation_always_true():
    scenarios = [
        # critical open
        _base_ctx_with_finding(severity="critical", status="open"),
        # high open
        _base_ctx_with_finding(severity="high", status="open"),
        # all clear
        _base_ctx(),
    ]
    for ctx in scenarios:
        decision = generate_deployment_decision(ctx)
        assert decision.is_demo_recommendation is True, (
            f"is_demo_recommendation must be True for {decision.decision}"
        )


def _base_ctx_with_finding(*, severity: str, status: str) -> ProjectContext:
    ctx = _base_ctx()
    ctx.safety_findings.append(_finding(severity=severity, status=status))
    return ctx


# ─────────────────────────────────────────────
# 7. Blocking pending action → conditional_go
# ─────────────────────────────────────────────


def test_blocking_action_produces_conditional_go():
    ctx = _base_ctx()
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id="sess-deploy",
            stage_id=3,
            action_type="approve",
            title="blocking action",
            description="must resolve",
            risk_level="high",
            blocking=True,
            status="pending",
        )
    )

    decision = generate_deployment_decision(ctx)
    assert decision.decision == "conditional_go"
    assert decision.required_conditions


# ─────────────────────────────────────────────
# 8. Unresolved risk IDs collection includes open findings + uncovered high FMs
# ─────────────────────────────────────────────


def test_unresolved_risk_ids_include_open_findings():
    ctx = _base_ctx()
    ctx.safety_findings.append(_finding(severity="high", status="open", finding_id="SAFE-OPEN-1"))
    ctx.safety_findings.append(
        _finding(severity="high", status="resolved", finding_id="SAFE-RESOLVED-1")
    )

    decision = generate_deployment_decision(ctx)
    assert "SAFE-OPEN-1" in decision.unresolved_risk_ids
    assert "SAFE-RESOLVED-1" not in decision.unresolved_risk_ids


def test_unresolved_risk_ids_include_uncovered_high_fms():
    ctx = _base_ctx()
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(id="FM-HIGH", category="...", description="...", severity="high"),
            FailureMode(id="FM-MED", category="...", description="...", severity="medium"),
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="NODE-1",
                stage_name="...",
                model_assigned="llm",
                human_action="approve",
                check_criteria="ok",
                failure_modes_addressed=["FM-MED"],  # does NOT cover FM-HIGH
                prompt_template="...",
            ),
        ]
    )

    decision = generate_deployment_decision(ctx)
    # FM-HIGH is uncovered → appears in unresolved_risk_ids
    assert "FM-HIGH" in decision.unresolved_risk_ids


# ─────────────────────────────────────────────
# 9. apply_deployment_decision writes to stage_4_output
# ─────────────────────────────────────────────


def test_apply_deployment_decision_writes_to_stage4():
    ctx = _base_ctx()
    ctx.safety_findings.append(_finding(severity="critical", status="open"))
    ctx.stage_4_output = Stage4Output()

    decision = apply_deployment_decision(ctx)
    assert decision is not None
    assert decision.decision == "no_go"
    assert ctx.stage_4_output.deployment_decision is not None
    assert ctx.stage_4_output.deployment_decision.decision == "no_go"


def test_apply_deployment_decision_no_stage4_returns_none():
    ctx = _base_ctx()
    assert apply_deployment_decision(ctx) is None
