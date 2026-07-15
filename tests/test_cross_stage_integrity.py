# tests/test_cross_stage_integrity.py
"""WS-7: CrossStageIntegrityRule unit tests.

Validates cross-stage ID reference integrity, high-risk test coverage, and
Stage 4 decision consistency. Uses ``rule.evaluate`` directly to avoid
side-effects from the full gate engine persistence path.
"""

from __future__ import annotations

from core.gates.rules.cross_stage_integrity import rule
from core.models import (
    DeploymentDecision,
    FailureMode,
    ProjectContext,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
    StressTestResult,
    WorkflowNode,
)

RULE_ID = "cross_stage_integrity"


def _blocker_messages(blockers) -> list[str]:
    return [b.message for b in blockers]


# ─────────────────────────────────────────────
# Context builders
# ─────────────────────────────────────────────


def _base_ctx() -> ProjectContext:
    ctx = ProjectContext()
    ctx.session_id = "sess-cross-stage"
    ctx.tenant_id = "tenant-cross"
    return ctx


def _valid_stage1() -> Stage1Output:
    return Stage1Output(
        failure_modes=[
            FailureMode(id="FM-A", category="幻觉", description="...", severity="high"),
            FailureMode(id="FM-B", category="权限", description="...", severity="medium"),
        ]
    )


def _valid_stage2() -> Stage2Output:
    return Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="NODE-1",
                stage_name="审核关卡",
                model_assigned="llm",
                human_action="approve",
                check_criteria="ok",
                failure_modes_addressed=["FM-A", "FM-B"],
                prompt_template="...",
            ),
        ]
    )


def _valid_stage3() -> Stage3Output:
    return Stage3Output(
        test_results=[
            StressTestResult(
                tested_node_id="NODE-1",
                test_input="...",
                ai_output="...",
                case_id="TC-1",
                failure_mode_id="FM-A",
                final_pass_status="passed",
                human_review_result="approved",
            ),
            StressTestResult(
                tested_node_id="NODE-1",
                test_input="...",
                ai_output="...",
                case_id="TC-2",
                failure_mode_id="FM-B",
                final_pass_status="passed",
                human_review_result="not_required",
            ),
        ]
    )


# ─────────────────────────────────────────────
# 1. Stage 2 referencing non-existent FM ID → blocker
# ─────────────────────────────────────────────


def test_stage2_invalid_fm_reference_blocks():
    ctx = _base_ctx()
    ctx.stage_1_output = _valid_stage1()
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="NODE-BAD",
                stage_name="bad node",
                model_assigned="llm",
                human_action="approve",
                check_criteria="ok",
                failure_modes_addressed=["FM-A", "FM-GHOST"],  # FM-GHOST does not exist
                prompt_template="...",
            ),
        ]
    )

    blockers = rule.evaluate(ctx, 2)
    csi_blockers = [b for b in blockers if b.rule_id == RULE_ID]
    assert len(csi_blockers) == 1, _blocker_messages(blockers)
    assert "FM-GHOST" in csi_blockers[0].message
    assert csi_blockers[0].severity == "high"
    assert csi_blockers[0].can_be_overridden_by_approval is False


# ─────────────────────────────────────────────
# 2. Stage 3 referencing non-existent FM or node ID → blocker
# ─────────────────────────────────────────────


def test_stage3_invalid_fm_reference_blocks():
    ctx = _base_ctx()
    ctx.stage_1_output = _valid_stage1()
    ctx.stage_2_output = _valid_stage2()
    ctx.stage_3_output = Stage3Output(
        test_results=[
            StressTestResult(
                tested_node_id="NODE-1",
                test_input="...",
                ai_output="...",
                case_id="TC-BAD",
                failure_mode_id="FM-GHOST",  # non-existent FM
                final_pass_status="passed",
            ),
        ]
    )

    blockers = rule.evaluate(ctx, 3)
    csi_blockers = [b for b in blockers if b.rule_id == RULE_ID]
    fm_blockers = [b for b in csi_blockers if "FM-GHOST" in b.message]
    assert len(fm_blockers) == 1, _blocker_messages(csi_blockers)


def test_stage3_invalid_node_reference_blocks():
    ctx = _base_ctx()
    ctx.stage_1_output = _valid_stage1()
    ctx.stage_2_output = _valid_stage2()
    ctx.stage_3_output = Stage3Output(
        test_results=[
            StressTestResult(
                tested_node_id="NODE-GHOST",  # non-existent node
                test_input="...",
                ai_output="...",
                case_id="TC-BAD",
                failure_mode_id="FM-A",
                final_pass_status="passed",
            ),
        ]
    )

    blockers = rule.evaluate(ctx, 3)
    csi_blockers = [b for b in blockers if b.rule_id == RULE_ID]
    node_blockers = [b for b in csi_blockers if "NODE-GHOST" in b.message]
    assert len(node_blockers) == 1, _blocker_messages(csi_blockers)


# ─────────────────────────────────────────────
# 3. High/critical FM not covered by Stage 3 test → blocker
# ─────────────────────────────────────────────


def test_uncovered_high_risk_fm_blocks():
    """A high/critical FM with no Stage 3 test result must produce a blocker."""
    ctx = _base_ctx()
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(id="FM-HIGH", category="...", description="...", severity="high"),
            FailureMode(id="FM-MED", category="...", description="...", severity="medium"),
        ]
    )
    ctx.stage_2_output = _valid_stage2()
    ctx.stage_3_output = Stage3Output(
        test_results=[
            StressTestResult(
                tested_node_id="NODE-1",
                test_input="...",
                ai_output="...",
                case_id="TC-1",
                failure_mode_id="FM-MED",  # only covers the medium FM
                final_pass_status="passed",
            ),
        ]
    )

    blockers = rule.evaluate(ctx, 3)
    csi_blockers = [b for b in blockers if b.rule_id == RULE_ID]
    coverage_blockers = [b for b in csi_blockers if "FM-HIGH" in b.message]
    assert len(coverage_blockers) == 1, _blocker_messages(csi_blockers)
    assert "高风险" in coverage_blockers[0].message or "没有对应" in coverage_blockers[0].message


# ─────────────────────────────────────────────
# 4. Stage 4 decision consistency → blocker
# ─────────────────────────────────────────────


def test_stage4_missing_deployment_decision_blocks():
    ctx = _base_ctx()
    ctx.stage_1_output = _valid_stage1()
    ctx.stage_2_output = _valid_stage2()
    ctx.stage_3_output = _valid_stage3()
    ctx.stage_4_output = Stage4Output()  # no deployment_decision

    blockers = rule.evaluate(ctx, 4)
    csi_blockers = [b for b in blockers if b.rule_id == RULE_ID]
    decision_blockers = [b for b in csi_blockers if "deployment_decision" in b.message]
    assert len(decision_blockers) == 1, _blocker_messages(csi_blockers)
    assert decision_blockers[0].severity == "critical"


def test_stage4_conditional_go_without_conditions_blocks():
    ctx = _base_ctx()
    ctx.stage_1_output = _valid_stage1()
    ctx.stage_2_output = _valid_stage2()
    ctx.stage_3_output = _valid_stage3()
    ctx.stage_4_output = Stage4Output(
        deployment_decision=DeploymentDecision(
            decision="conditional_go",
            decision_scope="conditional_deployment",
            required_conditions=[],  # empty → must block
            rollback_conditions=["rollback condition"],
        )
    )

    blockers = rule.evaluate(ctx, 4)
    csi_blockers = [b for b in blockers if b.rule_id == RULE_ID]
    cond_blockers = [b for b in csi_blockers if "conditional_go" in b.message]
    assert len(cond_blockers) == 1, _blocker_messages(csi_blockers)
    assert cond_blockers[0].severity == "high"


def test_stage4_pilot_only_without_rollback_blocks():
    ctx = _base_ctx()
    ctx.stage_1_output = _valid_stage1()
    ctx.stage_2_output = _valid_stage2()
    ctx.stage_3_output = _valid_stage3()
    ctx.stage_4_output = Stage4Output(
        deployment_decision=DeploymentDecision(
            decision="pilot_only",
            decision_scope="limited_pilot",
            required_conditions=["some condition"],
            rollback_conditions=[],  # empty → must block
        )
    )

    blockers = rule.evaluate(ctx, 4)
    csi_blockers = [b for b in blockers if b.rule_id == RULE_ID]
    rollback_blockers = [b for b in csi_blockers if "pilot_only" in b.message]
    assert len(rollback_blockers) == 1, _blocker_messages(csi_blockers)


# ─────────────────────────────────────────────
# 5. Valid cross-stage references → no blocker
# ─────────────────────────────────────────────


def test_valid_cross_stage_references_no_blocker():
    ctx = _base_ctx()
    ctx.stage_1_output = _valid_stage1()
    ctx.stage_2_output = _valid_stage2()
    ctx.stage_3_output = _valid_stage3()
    ctx.stage_4_output = Stage4Output(
        deployment_decision=DeploymentDecision(
            decision="pilot_only",
            decision_scope="limited_pilot",
            required_conditions=["pilot scope confirmed"],
            rollback_conditions=["stop on critical finding"],
        )
    )

    for stage in (2, 3, 4):
        blockers = rule.evaluate(ctx, stage)
        csi_blockers = [b for b in blockers if b.rule_id == RULE_ID]
        assert csi_blockers == [], (
            f"stage {stage}: unexpected blockers {_blocker_messages(csi_blockers)}"
        )


def test_rule_metadata():
    assert rule.rule_id == RULE_ID
    assert rule.applies_to_stages == {2, 3, 4}
    assert rule.applies_to(2) is True
    assert rule.applies_to(3) is True
    assert rule.applies_to(4) is True
    assert rule.applies_to(1) is False
