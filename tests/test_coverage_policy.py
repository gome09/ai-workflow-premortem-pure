# tests/test_coverage_policy.py
"""Milestone 2: risk-driven Stage 3 coverage policy."""

from __future__ import annotations

from core.config import settings
from core.coverage.policy import (
    build_coverage_policy,
    build_coverage_report,
    min_cases_for_tier,
    required_high_risk_node_ids,
    select_target_node_ids,
)
from core.gates.rules.stage3_eval_failure import Stage3EvalFailureRule
from core.models import (
    EvalCase,
    FailureMode,
    ProjectContext,
    RiskFactorScores,
    SessionState,
    Stage1Output,
    Stage2Output,
    WorkflowNode,
)
from core.risk.models import ProjectGateRiskTier
from stages.stage_3_stress_test import Stage3Executor

_LOW = RiskFactorScores(
    impact=0, autonomy=0, data_sensitivity=0, reversibility=0, scale=0, external_exposure=0
)
_MEDIUM = RiskFactorScores(
    impact=1, autonomy=1, data_sensitivity=1, reversibility=1, scale=1, external_exposure=1
)
_HIGH = RiskFactorScores(
    impact=2, autonomy=1, data_sensitivity=2, reversibility=2, scale=1, external_exposure=1
)
_CRITICAL = RiskFactorScores(
    impact=3, autonomy=2, data_sensitivity=3, reversibility=2, scale=2, external_exposure=1
)


def _node(node_id: str, addressed: list[str]) -> WorkflowNode:
    return WorkflowNode(
        node_id=node_id,
        stage_name=f"stage {node_id}",
        model_assigned="llm",
        human_action="review",
        check_criteria="ok",
        failure_modes_addressed=addressed,
        prompt_template="prompt",
    )


def _build_ctx(tier: RiskFactorScores, node_count: int = 6) -> ProjectContext:
    failure_modes = [
        FailureMode(id="FM-CRIT", category="c", description="d", severity="critical"),
        FailureMode(id="FM-HIGH", category="c", description="d", severity="high"),
        FailureMode(id="FM-MED", category="c", description="d", severity="medium"),
        FailureMode(id="FM-LOW", category="c", description="d", severity="low"),
    ]
    nodes = [
        _node("N1", ["FM-CRIT"]),
        _node("N2", ["FM-HIGH"]),
        _node("N3", ["FM-MED"]),
        _node("N4", []),
        _node("N5", ["FM-CRIT", "FM-HIGH"]),
        _node("N6", ["FM-LOW"]),
    ]
    for index in range(7, node_count + 1):
        nodes.append(_node(f"N{index}", ["FM-LOW"]))
    ctx = ProjectContext(
        research_target="coverage policy test",
        current_state=SessionState.S3_REVIEW,
        risk_profile=tier,
    )
    ctx.stage_1_output = Stage1Output(failure_modes=failure_modes)
    ctx.stage_2_output = Stage2Output(workflow_nodes=nodes)
    return ctx


def _set_coverage(monkeypatch, *, low=3, medium=5, high=5, ratio=0.2, min_cases=1):
    monkeypatch.setattr(settings, "stage3_low_risk_sample_nodes", low)
    monkeypatch.setattr(settings, "stage3_medium_risk_sample_nodes", medium)
    monkeypatch.setattr(settings, "stage3_high_risk_sample_nodes", high)
    monkeypatch.setattr(settings, "stage3_min_coverage_ratio", ratio)
    monkeypatch.setattr(settings, "stage3_min_cases_per_high_risk_node", min_cases)


def test_high_risk_required_nodes_always_selected_even_with_tiny_budget(monkeypatch):
    _set_coverage(monkeypatch, high=1, ratio=0.0)
    ctx = _build_ctx(_HIGH)
    policy = build_coverage_policy(ctx)
    assert set(policy.required_node_ids) == {"N1", "N2", "N5"}
    assert set(policy.required_node_ids).issubset(set(policy.selected_node_ids))
    assert len(policy.selected_node_ids) >= 3


def test_critical_selects_every_node(monkeypatch):
    _set_coverage(monkeypatch, high=1, ratio=0.0)
    ctx = _build_ctx(_CRITICAL, node_count=10)
    policy = build_coverage_policy(ctx)
    assert policy.risk_tier.value == "critical"
    assert set(policy.selected_node_ids) == {
        node.node_id for node in ctx.stage_2_output.workflow_nodes
    }


def test_medium_budget_respects_minimum_coverage_ratio(monkeypatch):
    _set_coverage(monkeypatch, medium=2, ratio=0.5)
    ctx = _build_ctx(_MEDIUM, node_count=10)
    policy = build_coverage_policy(ctx)
    expected_budget = max(2, 5)
    assert len(policy.selected_node_ids) == expected_budget
    assert set(policy.required_node_ids).issubset(set(policy.selected_node_ids))


def test_low_budget_uses_max_of_configured_sample_and_ratio(monkeypatch):
    _set_coverage(monkeypatch, low=2, ratio=0.5)
    ctx = _build_ctx(_LOW, node_count=10)
    policy = build_coverage_policy(ctx)
    # LOW only requires critical-failure-mode nodes.
    assert set(policy.required_node_ids) == {"N1", "N5"}
    assert len(policy.selected_node_ids) == 5
    assert set(policy.required_node_ids).issubset(set(policy.selected_node_ids))


def test_selection_is_deterministic():
    ctx = _build_ctx(_HIGH, node_count=10)
    first = select_target_node_ids(ctx)
    assert all(select_target_node_ids(ctx) == first for _ in range(20))


def test_stage3_executor_uses_coverage_policy(monkeypatch):
    _set_coverage(monkeypatch, high=1, ratio=0.0)
    ctx = _build_ctx(_HIGH)
    selected = [node.node_id for node in Stage3Executor()._select_target_nodes(ctx)]
    assert selected == select_target_node_ids(ctx)


def test_high_risk_gate_blocks_missing_cases_then_passes(monkeypatch):
    _set_coverage(monkeypatch, high=5, ratio=0.2, min_cases=1)
    ctx = _build_ctx(_HIGH)
    rule = Stage3EvalFailureRule()
    missing = [
        blocker for blocker in rule.evaluate(ctx, 3) if blocker.source_type == "eval_coverage"
    ]
    assert {blocker.source_id for blocker in missing} == {"N1", "N2", "N5"}

    for node_id in ("N1", "N2", "N5"):
        ctx.eval_cases.append(
            EvalCase(
                session_id=ctx.session_id,
                target_node_id=node_id,
                scenario_type="normal",
                input_payload="x",
                expected_behavior="y",
                passed=True,
            )
        )
    remaining = [
        blocker for blocker in rule.evaluate(ctx, 3) if blocker.source_type == "eval_coverage"
    ]
    assert remaining == []


def test_high_risk_gate_enforces_configured_min_cases(monkeypatch):
    _set_coverage(monkeypatch, min_cases=2)
    ctx = _build_ctx(_HIGH)
    ctx.eval_cases.append(
        EvalCase(
            session_id=ctx.session_id,
            target_node_id="N1",
            scenario_type="normal",
            input_payload="x",
            expected_behavior="y",
            passed=True,
        )
    )
    blockers = [
        blocker
        for blocker in Stage3EvalFailureRule().evaluate(ctx, 3)
        if blocker.source_type == "eval_coverage"
    ]
    assert {blocker.source_id for blocker in blockers} == {"N1", "N2", "N5"}
    assert min_cases_for_tier(ProjectGateRiskTier.HIGH) == 2


def test_coverage_report_shares_high_risk_node_definition(monkeypatch):
    _set_coverage(monkeypatch, min_cases=1)
    ctx = _build_ctx(_HIGH)
    report = build_coverage_report(ctx)
    assert set(report["required_node_ids"]) == required_high_risk_node_ids(ctx)

    from core.eval_service import build_eval_summary
    from core.redteam_service import _high_risk_node_ids as redteam_high_nodes
    from core.stage_readiness_service import _high_risk_node_ids as readiness_high_nodes

    assert redteam_high_nodes(ctx) == required_high_risk_node_ids(ctx)
    assert readiness_high_nodes(ctx) == required_high_risk_node_ids(ctx)
    assert build_eval_summary(ctx)["high_risk_node_coverage"]["total_high_risk_nodes"] == len(
        required_high_risk_node_ids(ctx)
    )


def test_empty_workflow_nodes_is_stable():
    ctx = ProjectContext(research_target="empty", risk_profile=_HIGH)
    policy = build_coverage_policy(ctx)
    assert policy.selected_node_ids == []
    assert build_coverage_report(ctx)["missing_required_node_ids"] == []
