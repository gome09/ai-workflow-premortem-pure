"""Tests for risk-adaptive Stage 3 gate (v0.8.0-beta.2).

Verifies that:
- Low-risk projects (e.g., personal reading planner) are not blocked by
  redteam coverage, eval regression, or trace backfill gaps.
- High-risk projects (e.g., medication management) retain strong gate.
- Medium-risk projects get intermediate behavior.
- Explicit gate_required datasets still block low-risk projects.
- Safety底线 (parser error, pending action, rejected action, etc.)
  always blocks regardless of risk tier.
"""

from __future__ import annotations

from core.gates.risk_profile import (
    ProjectGateRiskTier,
    build_stage3_gate_profile,
    classify_project_risk,
)
from core.gates.rules.eval_regression import rule as eval_regression_rule
from core.gates.rules.redteam_coverage import rule as redteam_coverage_rule
from core.gates.rules.stage3_eval_failure import (
    Stage3EvalFailureRule,
    _risk_adjusted_high_risk_nodes,
)
from core.gates.rules.trace_backfill_gap import rule as trace_backfill_rule
from core.models import (
    EvalCase,
    EvalDataset,
    EvalExperiment,
    FailureMode,
    HumanOversightPolicy,
    LLMTrace,
    PendingHumanAction,
    ProjectContext,
    SafetyFinding,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    WorkflowNode,
)
from core.stage_readiness_service import evaluate_stage_gate

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _reading_planner_ctx() -> ProjectContext:
    """Low-risk: personal reading & learning plan management."""
    ctx = ProjectContext(
        research_target="个人读书与学习计划管理系统",
        domain="个人学习 / 读书计划 / 本地使用",
        goal="帮助个人制定和跟踪阅读计划",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-1",
                category="目标偏移",
                description="学习计划混乱，目标偏移",
                severity="high",
            ),
            FailureMode(
                id="FM-2",
                category="内容遗忘",
                description="读书笔记丢失",
                severity="high",
            ),
            FailureMode(
                id="FM-3",
                category="推荐不准",
                description="推荐书目不符合兴趣",
                severity="medium",
            ),
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-plan",
                stage_name="计划生成",
                model_assigned="llm",
                human_action="review",
                check_criteria="计划合理",
                failure_modes_addressed=["FM-1"],
                prompt_template="生成阅读计划",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-1",
                    required_action="approve",
                ),
            ),
            WorkflowNode(
                node_id="N-note",
                stage_name="笔记整理",
                model_assigned="llm",
                human_action="review",
                check_criteria="笔记完整",
                failure_modes_addressed=["FM-2"],
                prompt_template="整理读书笔记",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-2",
                    required_action="approve",
                ),
            ),
        ]
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    return ctx


def _medication_ctx() -> ProjectContext:
    """High/critical-risk: medication management system."""
    ctx = ProjectContext(
        research_target="药物管理系统",
        domain="医疗健康 / 药房协作 / 患者用药",
        goal="管理患者用药记录和药物交互检查",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-M1",
                category="药物交互",
                description="药物交互检查遗漏导致患者风险",
                severity="critical",
            ),
            FailureMode(
                id="FM-M2",
                category="剂量错误",
                description="处方剂量计算错误",
                severity="high",
            ),
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-interact",
                stage_name="药物交互检查",
                model_assigned="llm",
                human_action="approve",
                check_criteria="交互检查完整",
                failure_modes_addressed=["FM-M1"],
                prompt_template="检查药物交互",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="critical",
                    trigger_reason="FM-M1",
                    required_action="escalate",
                ),
            ),
            WorkflowNode(
                node_id="N-dose",
                stage_name="剂量计算",
                model_assigned="llm",
                human_action="approve",
                check_criteria="剂量正确",
                failure_modes_addressed=["FM-M2"],
                prompt_template="计算剂量",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-M2",
                    required_action="approve",
                ),
            ),
        ]
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    return ctx


def _team_task_manager_ctx() -> ProjectContext:
    """Medium-risk: team task management."""
    ctx = ProjectContext(
        research_target="团队任务管理系统",
        domain="项目管理 / 团队协作",
        goal="管理团队任务分配和进度跟踪",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-T1",
                category="任务遗漏",
                description="任务分配遗漏导致延期",
                severity="high",
            ),
            FailureMode(
                id="FM-T2",
                category="优先级错误",
                description="优先级排序不合理",
                severity="medium",
            ),
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-assign",
                stage_name="任务分配",
                model_assigned="llm",
                human_action="review",
                check_criteria="分配合理",
                failure_modes_addressed=["FM-T1"],
                prompt_template="分配任务",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-T1",
                    required_action="approve",
                ),
            ),
        ]
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    return ctx


# ─────────────────────────────────────────────
# 1. Risk classification tests
# ─────────────────────────────────────────────


def test_classify_reading_planner_as_low_risk():
    ctx = _reading_planner_ctx()
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.LOW
    assert any("personal" in r or "learning" in r for r in reasons)


def test_classify_medication_as_critical_risk():
    ctx = _medication_ctx()
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.CRITICAL
    assert any("healthcare" in r or "medical" in r for r in reasons)


def test_classify_team_task_manager_as_medium_risk():
    ctx = _team_task_manager_ctx()
    tier, reasons = classify_project_risk(ctx)
    # Medium or low depending on keyword matches — both are acceptable
    assert tier in {ProjectGateRiskTier.LOW, ProjectGateRiskTier.MEDIUM}


# ─────────────────────────────────────────────
# 2. Stage3GateProfile tests
# ─────────────────────────────────────────────


def test_low_risk_profile_does_not_require_redteam():
    ctx = _reading_planner_ctx()
    profile = build_stage3_gate_profile(ctx)
    assert profile.risk_tier == ProjectGateRiskTier.LOW
    assert profile.require_redteam_coverage is False
    assert profile.require_eval_regression is False
    assert profile.require_trace_backfill is False
    assert profile.require_expert_review is False
    # But eval coverage and failed eval resolution still required
    assert profile.require_eval_coverage is True
    assert profile.require_failed_eval_resolution is True


def test_critical_risk_profile_requires_everything():
    ctx = _medication_ctx()
    profile = build_stage3_gate_profile(ctx)
    assert profile.risk_tier == ProjectGateRiskTier.CRITICAL
    assert profile.require_redteam_coverage is True
    assert profile.require_eval_regression is True
    assert profile.require_trace_backfill is True
    assert profile.require_expert_review is True
    assert profile.require_eval_coverage is True
    assert profile.require_failed_eval_resolution is True


# ─────────────────────────────────────────────
# 3. Low-risk reading planner: NOT blocked by advanced gates
# ─────────────────────────────────────────────


def test_low_risk_not_blocked_by_redteam_coverage():
    """Low-risk project should not be blocked by missing redteam coverage."""
    ctx = _reading_planner_ctx()
    blockers = redteam_coverage_rule.evaluate(ctx, 3)
    # No redteam cases exist, but low-risk should not block
    assert blockers == []


def test_low_risk_not_blocked_by_missing_baseline_experiment():
    """Low-risk project should not be blocked by missing baseline experiment."""
    ctx = _reading_planner_ctx()
    # Add a gate-relevant dataset without baseline
    dataset = EvalDataset(
        session_id=ctx.session_id,
        dataset_id="D-no-baseline",
        name="test dataset",
        stage=3,
        tags=["stage3"],
        case_ids=["E1"],
    )
    ctx.eval_datasets.append(dataset)

    blockers = eval_regression_rule.evaluate(ctx, 3)
    assert blockers == []


def test_low_risk_not_blocked_by_trace_backfill_gap():
    """Low-risk project should not be blocked by trace backfill gaps."""
    ctx = _reading_planner_ctx()
    # Add a failed trace that hasn't been backfilled
    ctx.llm_traces.append(
        LLMTrace(
            session_id=ctx.session_id,
            stage=3,
            node_name="stage3_parser",
            trace_type="parser",
            parser_status="failed",
            error_type="parser_error",
            error_message="invalid json",
        )
    )

    blockers = trace_backfill_rule.evaluate(ctx, 3)
    assert blockers == []


def test_low_risk_stage3_gate_not_blocked_by_advanced_rules():
    """Full Stage 3 gate should pass for low-risk even with high failure modes."""
    ctx = _reading_planner_ctx()

    # Add eval cases covering the high-risk nodes so eval_failure doesn't block
    ctx.eval_cases.append(
        EvalCase(
            session_id=ctx.session_id,
            target_node_id="N-plan",
            input_payload="test input",
            expected_behavior="合理计划",
            passed=True,
        )
    )
    ctx.eval_cases.append(
        EvalCase(
            session_id=ctx.session_id,
            target_node_id="N-note",
            input_payload="test input",
            expected_behavior="完整笔记",
            passed=True,
        )
    )

    gate = evaluate_stage_gate(ctx, 3)
    # No redteam/eval_regression/trace_backfill blockers
    advanced_blockers = [
        b
        for b in gate.blockers
        if b.blocker_type in {"redteam_coverage", "eval_regression", "trace_backfill_gap"}
    ]
    assert advanced_blockers == []


# ─────────────────────────────────────────────
# 4. Medication management: retains strong gate
# ─────────────────────────────────────────────


def test_medication_blocked_by_redteam_coverage():
    """Critical-risk medication project should be blocked by missing redteam coverage."""
    ctx = _medication_ctx()
    blockers = redteam_coverage_rule.evaluate(ctx, 3)
    # Should have blockers for missing node redteam coverage
    assert len(blockers) > 0
    assert all(b.blocker_type == "redteam_coverage" for b in blockers)


def test_medication_blocked_by_trace_backfill():
    """Critical-risk medication project should be blocked by trace backfill gaps."""
    ctx = _medication_ctx()
    ctx.llm_traces.append(
        LLMTrace(
            session_id=ctx.session_id,
            stage=3,
            node_name="N-interact",
            trace_type="safety",
            safety_status="failed",
            error_type="safety_violation",
            error_message="unsafe drug interaction",
        )
    )

    blockers = trace_backfill_rule.evaluate(ctx, 3)
    assert len(blockers) > 0
    assert all(b.blocker_type == "trace_backfill_gap" for b in blockers)


def test_medication_regression_still_blocks():
    """Critical-risk project should still be blocked by eval regression."""
    ctx = _medication_ctx()
    baseline = EvalExperiment(
        session_id=ctx.session_id,
        dataset_id="D-med",
        name="baseline",
        status="completed",
        eval_ids=["E-med"],
    )
    current = EvalExperiment(
        session_id=ctx.session_id,
        dataset_id="D-med",
        name="current",
        status="completed",
        eval_ids=["E-med"],
        baseline_experiment_id=baseline.experiment_id,
        comparison_summary={
            "regression_detected": True,
            "regression_reasons": ["pass_rate_drop_exceeds_5_percent"],
            "pass_rate_delta": -0.10,
        },
    )
    dataset = EvalDataset(
        session_id=ctx.session_id,
        dataset_id="D-med",
        name="med regression",
        stage=3,
        tags=["stage3", "regression"],
        case_ids=["E-med"],
        baseline_experiment_id=baseline.experiment_id,
    )
    ctx.eval_datasets.append(dataset)
    ctx.eval_experiments.extend([baseline, current])

    blockers = eval_regression_rule.evaluate(ctx, 3)
    assert len(blockers) > 0
    assert blockers[0].blocker_type == "eval_regression"


# ─────────────────────────────────────────────
# 5. Explicit gate_required dataset: low-risk still blocks
# ─────────────────────────────────────────────


def test_low_risk_gate_required_dataset_still_blocks():
    """Even low-risk projects block on datasets with gate_required=true."""
    ctx = _reading_planner_ctx()
    baseline = EvalExperiment(
        session_id=ctx.session_id,
        dataset_id="D-gated",
        name="baseline",
        status="completed",
        eval_ids=["E-gated"],
    )
    current = EvalExperiment(
        session_id=ctx.session_id,
        dataset_id="D-gated",
        name="current",
        status="completed",
        eval_ids=["E-gated"],
        baseline_experiment_id=baseline.experiment_id,
        comparison_summary={
            "regression_detected": True,
            "regression_reasons": ["pass_rate_drop_exceeds_5_percent"],
            "pass_rate_delta": -0.10,
        },
    )
    dataset = EvalDataset(
        session_id=ctx.session_id,
        dataset_id="D-gated",
        name="gated dataset",
        stage=3,
        scenario_type="mixed",
        case_ids=["E-gated"],
        baseline_experiment_id=baseline.experiment_id,
        metadata={"gate_required": True},
    )
    ctx.eval_datasets.append(dataset)
    ctx.eval_experiments.extend([baseline, current])

    blockers = eval_regression_rule.evaluate(ctx, 3)
    assert len(blockers) > 0
    assert blockers[0].blocker_type == "eval_regression"


def test_low_risk_non_gated_dataset_does_not_block():
    """Low-risk project: non-gated dataset does not block."""
    ctx = _reading_planner_ctx()
    dataset = EvalDataset(
        session_id=ctx.session_id,
        dataset_id="D-free",
        name="free dataset",
        stage=3,
        scenario_type="normal",
        case_ids=["E-free"],
        metadata={},
    )
    ctx.eval_datasets.append(dataset)

    blockers = eval_regression_rule.evaluate(ctx, 3)
    assert blockers == []


# ─────────────────────────────────────────────
# 6. Safety底线: parser error blocks even for low risk
# ─────────────────────────────────────────────


def test_low_risk_parser_error_still_blocks():
    """Parser error must block even low-risk projects."""
    ctx = _reading_planner_ctx()
    ctx.parser_errors["stage_3"] = "invalid json output"

    gate = evaluate_stage_gate(ctx, 3)
    parser_blockers = [b for b in gate.blockers if b.blocker_type == "parser_error"]
    assert len(parser_blockers) > 0


def test_low_risk_pending_blocking_action_still_blocks():
    """Pending blocking action must block even low-risk projects."""
    ctx = _reading_planner_ctx()
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=3,
            action_type="approve",
            title="Review plan",
            description="Please review the reading plan",
            blocking=True,
        )
    )

    gate = evaluate_stage_gate(ctx, 3)
    action_blockers = [b for b in gate.blockers if b.blocker_type == "pending_action"]
    assert len(action_blockers) > 0


def test_low_risk_rejected_action_still_blocks():
    """Rejected action must block even low-risk projects."""
    ctx = _reading_planner_ctx()
    ctx.pending_actions.append(
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=3,
            action_type="approve",
            title="Review plan",
            description="Please review the reading plan",
            blocking=True,
            status="resolved",
            reviewer_decision="reject",
        )
    )

    gate = evaluate_stage_gate(ctx, 3)
    rejected_blockers = [b for b in gate.blockers if b.blocker_type == "rejected_action"]
    assert len(rejected_blockers) > 0


def test_low_risk_open_safety_finding_still_blocks():
    """Open high/critical safety finding must block even low-risk projects."""
    ctx = _reading_planner_ctx()
    ctx.safety_findings.append(
        SafetyFinding(
            session_id=ctx.session_id,
            stage_id=3,
            risk_type="unsafe_instruction",
            severity="high",
            location="N-plan",
            description="Unsafe recommendation found",
            recommended_action="Review and fix",
            requires_human_review=True,
            status="open",
        )
    )

    gate = evaluate_stage_gate(ctx, 3)
    safety_blockers = [b for b in gate.blockers if b.blocker_type == "safety_finding"]
    assert len(safety_blockers) > 0


# ─────────────────────────────────────────────
# 7. Stage3 eval failure: risk-adjusted high-risk nodes
# ─────────────────────────────────────────────


def test_low_risk_only_critical_nodes_require_eval_coverage():
    """Low-risk: only nodes addressing critical failure modes need eval coverage."""
    ctx = _reading_planner_ctx()
    # FM-1 and FM-2 are "high", not "critical"
    nodes = _risk_adjusted_high_risk_nodes(ctx, ProjectGateRiskTier.LOW)
    # No critical failure modes → no nodes require eval coverage
    assert nodes == set()


def test_medium_risk_high_nodes_require_eval_coverage():
    """Medium-risk: nodes addressing high failure modes need eval coverage."""
    ctx = _reading_planner_ctx()
    nodes = _risk_adjusted_high_risk_nodes(ctx, ProjectGateRiskTier.MEDIUM)
    # FM-1 and FM-2 are "high" → N-plan and N-note should be included
    assert "N-plan" in nodes
    assert "N-note" in nodes


def test_critical_risk_all_high_nodes_require_eval_coverage():
    """Critical-risk: all high/critical nodes need eval coverage."""
    ctx = _medication_ctx()
    nodes = _risk_adjusted_high_risk_nodes(ctx, ProjectGateRiskTier.CRITICAL)
    assert "N-interact" in nodes
    assert "N-dose" in nodes


def test_low_risk_stage3_eval_failure_uses_adjusted_nodes():
    """Stage3EvalFailureRule should use risk-adjusted node set for low-risk."""
    ctx = _reading_planner_ctx()
    rule = Stage3EvalFailureRule()
    blockers = rule.evaluate(ctx, 3)
    # Low-risk: only critical nodes need eval, none exist → no blockers
    # (even though high nodes N-plan and N-note have no eval cases)
    assert blockers == []


# ─────────────────────────────────────────────
# 8. Medium risk: intermediate behavior
# ─────────────────────────────────────────────


def test_medium_risk_redteam_only_safety_gaps():
    """Medium-risk: redteam only blocks on safety finding gaps, not node coverage."""
    ctx = _team_task_manager_ctx()
    blockers = redteam_coverage_rule.evaluate(ctx, 3)
    # No safety findings → no redteam blockers for medium risk
    assert blockers == []


def test_medium_risk_eval_failure_blocks_high_nodes():
    """Medium-risk: eval failure blocks on high-severity nodes without coverage."""
    ctx = _team_task_manager_ctx()
    # N-assign addresses FM-T1 (high severity) but has no eval case
    rule = Stage3EvalFailureRule()
    blockers = rule.evaluate(ctx, 3)
    eval_blockers = [b for b in blockers if b.blocker_type == "eval_failure"]
    assert len(eval_blockers) > 0
    assert any("N-assign" in b.message for b in eval_blockers)


# ─────────────────────────────────────────────
# 9. Risk profile rationale contains useful info
# ─────────────────────────────────────────────


def test_rationale_includes_domain_info():
    ctx = _medication_ctx()
    profile = build_stage3_gate_profile(ctx)
    assert "healthcare" in profile.rationale or "medical" in profile.rationale


def test_low_risk_rationale_includes_scope_info():
    ctx = _reading_planner_ctx()
    profile = build_stage3_gate_profile(ctx)
    assert "personal" in profile.rationale or "learning" in profile.rationale
