from core.models import (
    FailureMode,
    HumanOversightPolicy,
    ProjectContext,
    Stage1Output,
    Stage2Output,
    WorkflowNode,
)
from core.redteam_service import generate_redteam_cases


def test_generate_redteam_cases_from_high_risk_failure_mode():
    ctx = ProjectContext()
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-1",
                category="hallucination",
                description="model invents unsupported legal citations",
                severity="high",
            )
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-1",
                stage_name="draft",
                model_assigned="llm",
                human_action="review",
                check_criteria="citations verified",
                failure_modes_addressed=["FM-1"],
                prompt_template="draft with citations",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-1",
                    required_action="approve",
                ),
            )
        ]
    )

    created = generate_redteam_cases(ctx, stage=3)

    assert len(created) == 1
    assert created[0].source_failure_mode_id == "FM-1"
    assert created[0].target_node_id == "N-1"
    assert created[0].status == "draft"
