from core.gates.rules.redteam_coverage import rule
from core.models import (
    FailureMode,
    HumanOversightPolicy,
    ProjectContext,
    Stage1Output,
    Stage2Output,
    WorkflowNode,
)
from core.redteam_service import (
    approve_redteam_case,
    create_redteam_dataset,
    generate_redteam_cases,
    redteam_case_to_eval_case,
)


def _ctx_with_high_risk_node():
    ctx = ProjectContext(
        research_target="金融投资风险评估系统",
        domain="金融 / 投资 / 风险管理",
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[FailureMode(id="FM-1", category="x", description="risk", severity="high")]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-1",
                stage_name="node",
                model_assigned="llm",
                human_action="review",
                check_criteria="check",
                failure_modes_addressed=["FM-1"],
                prompt_template="prompt",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-1",
                    required_action="approve",
                ),
            )
        ]
    )
    return ctx


def test_redteam_coverage_gate_blocks_until_dataset_created():
    ctx = _ctx_with_high_risk_node()

    assert rule.evaluate(ctx, 3)

    cases = generate_redteam_cases(ctx, stage=3)
    assert rule.evaluate(ctx, 3)

    approve_redteam_case(ctx, cases[0].redteam_case_id)
    assert rule.evaluate(ctx, 3)

    redteam_case_to_eval_case(ctx, cases[0].redteam_case_id)
    assert rule.evaluate(ctx, 3)

    create_redteam_dataset(ctx)
    assert rule.evaluate(ctx, 3) == []
