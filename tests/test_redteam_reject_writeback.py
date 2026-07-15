from core.gates.rules.redteam_coverage import rule
from core.models import (
    FailureMode,
    HumanOversightPolicy,
    ProjectContext,
    Stage1Output,
    Stage2Output,
    WorkflowNode,
)
from core.oversight_service import create_review_actions_for_stage, resolve_action
from core.redteam_service import (
    approve_redteam_case,
    build_redteam_coverage_summary,
    generate_redteam_cases,
    get_redteam_case,
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


def _find_draft_case_action(ctx):
    for action in ctx.pending_actions:
        if action.source_type != "redteam_case":
            continue
        payload = action.payload_before or {}
        if payload.get("gap_type") == "draft_redteam_case":
            return action
    return None


def test_reject_redteam_case_action_writes_back_case_status():
    ctx = _ctx_with_high_risk_node()

    # 阶段三红队覆盖阻断器应先被触发（存在高风险 failure_mode/node 但无覆盖）。
    assert rule.evaluate(ctx, 3)

    generate_redteam_cases(ctx, stage=3)
    create_review_actions_for_stage(ctx, stage=3)

    action = _find_draft_case_action(ctx)
    assert action is not None, "expected a draft_redteam_case action to be created"

    case_id = (action.payload_before or {}).get("case_id") or action.source_id
    case_before = get_redteam_case(ctx, case_id)
    assert case_before.status == "draft"

    resolve_action(ctx, action_id=action.action_id, decision="reject", note="不需要该用例")

    case_after = get_redteam_case(ctx, case_id)
    assert case_after.status == "rejected"

    summary = build_redteam_coverage_summary(ctx, stage=3)
    assert case_id not in (summary.get("draft_high_case_ids") or [])
    assert case_id not in (summary.get("approved_unsynced_case_ids") or [])


def test_reject_approved_unsynced_redteam_case_action_writes_back_case_status():
    # 覆盖 approved_redteam_case_not_synced 分支：case 已 approved 但被驳回同步动作。
    ctx = _ctx_with_high_risk_node()
    cases = generate_redteam_cases(ctx, stage=3)
    approve_redteam_case(ctx, cases[0].redteam_case_id)
    create_review_actions_for_stage(ctx, stage=3)

    action = None
    for candidate in ctx.pending_actions:
        payload = candidate.payload_before or {}
        if (
            candidate.source_type == "redteam_case"
            and payload.get("gap_type") == "approved_redteam_case_not_synced"
        ):
            action = candidate
            break
    assert action is not None, "expected an approved_redteam_case_not_synced action to be created"

    case_id = (action.payload_before or {}).get("case_id") or action.source_id
    assert get_redteam_case(ctx, case_id).status == "approved"

    resolve_action(ctx, action_id=action.action_id, decision="reject", note="")

    case_after = get_redteam_case(ctx, case_id)
    assert case_after.status == "rejected"

    summary = build_redteam_coverage_summary(ctx, stage=3)
    assert case_id not in (summary.get("approved_unsynced_case_ids") or [])
