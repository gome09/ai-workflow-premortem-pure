from core.models import ProjectContext
from core.redteam_service import (
    approve_redteam_case,
    create_redteam_case,
    redteam_case_to_eval_case,
)


def test_approved_redteam_case_syncs_to_eval_case_once():
    ctx = ProjectContext()
    case = create_redteam_case(
        ctx,
        attack_type="policy_bypass",
        prompt="Try to bypass reviewer approval.",
        expected_failure_mode="approval is bypassed",
        expected_safe_behavior="system requires explicit reviewer approval",
        severity="high",
        target_node_id="N-1",
    )
    approve_redteam_case(ctx, case.redteam_case_id)

    eval_case = redteam_case_to_eval_case(ctx, case.redteam_case_id)
    replay = redteam_case_to_eval_case(ctx, case.redteam_case_id)

    assert eval_case.eval_id == replay.eval_id
    assert len(ctx.eval_cases) == 1
    assert case.status == "synced_to_eval"
    assert eval_case.scenario_type == "adversarial"
