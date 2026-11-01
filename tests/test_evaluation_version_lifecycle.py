"""Evaluation-version 2.0 lifecycle: immutable case binding and dependency invalidation."""

from __future__ import annotations

from dataclasses import replace

from core.eval_service import update_eval_case_standard
from core.evaluation_version import (
    INPUT_VERSION_KEY_TARGET_DEPLOYMENT,
    build_evaluation_version,
    bump_input_version,
    current_evaluation_digest,
    eval_case_digest,
)
from core.gates.rules.manifest import RULE_MANIFEST
from core.models import (
    EvalCase,
    EvalRun,
    ProjectApproval,
    ProjectContext,
    RiskTreatment,
    TargetDeployment,
)


def _ctx() -> ProjectContext:
    ctx = ProjectContext(
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        data_classification="business_internal",
    )
    case = EvalCase(
        session_id=ctx.session_id,
        stage_id=3,
        target_node_id="N-1",
        scenario_type="normal",
        input_payload="policy question",
        expected_behavior="answer with citation",
        pass_criteria=["citation present"],
    )
    ctx.eval_cases.append(case)
    ctx.target_deployment = TargetDeployment(endpoint="http://target.local/eval", version="v1")
    return ctx


def _run(ctx: ProjectContext, case: EvalCase) -> EvalRun:
    return EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        target_node_id=case.target_node_id,
        run_mode="target_http",
        execution_kind="real_target_execution",
        execution_outcome="success",
        evaluation_version_digest=current_evaluation_digest(ctx),
        target_endpoint=ctx.target_deployment.endpoint,
        target_deployment_version=ctx.target_deployment.version,
        case_version_digest=eval_case_digest(case),
        input_payload=case.input_payload,
        expected_behavior=case.expected_behavior,
        pass_criteria=list(case.pass_criteria),
        actual_output="answer with citation",
        judge_result="passed",
        status="completed",
    )


def test_case_standard_change_bumps_version_and_invalidates_old_run():
    ctx = _ctx()
    case = ctx.eval_cases[0]
    old_digest = current_evaluation_digest(ctx)
    old_case_digest = eval_case_digest(case)
    old_run = _run(ctx, case)
    ctx.eval_runs.append(old_run)

    update_eval_case_standard(
        ctx,
        eval_id=case.eval_id,
        updates={"pass_criteria": ["citation present", "no invented clause"]},
    )

    assert case.standard_version == 2
    assert current_evaluation_digest(ctx) != old_digest
    assert eval_case_digest(case) != old_case_digest
    assert old_run.case_version_digest != eval_case_digest(case)

    new_run = _run(ctx, case)
    assert new_run.pass_criteria == ["citation present", "no invented clause"]
    assert new_run.case_version_digest == eval_case_digest(case)
    assert new_run.evaluation_version_digest == current_evaluation_digest(ctx)


def test_standard_version_change_alone_changes_case_digest():
    ctx = _ctx()
    case = ctx.eval_cases[0]
    before = eval_case_digest(case)
    case.standard_version += 1
    assert eval_case_digest(case) != before


def test_materials_and_target_deployment_versions_change_digest():
    ctx = _ctx()
    before = current_evaluation_digest(ctx)

    ctx.user_materials.append("new user material")
    bump_input_version(ctx, "materials")
    assert current_evaluation_digest(ctx) != before

    after_material = current_evaluation_digest(ctx)
    ctx.target_deployment.version = "v2"
    bump_input_version(ctx, INPUT_VERSION_KEY_TARGET_DEPLOYMENT)
    assert current_evaluation_digest(ctx) != after_material
    assert ctx.input_versions[INPUT_VERSION_KEY_TARGET_DEPLOYMENT] == 1


def test_adding_run_treatment_or_approval_does_not_change_evaluation_digest():
    ctx = _ctx()
    case = ctx.eval_cases[0]
    before = current_evaluation_digest(ctx)

    ctx.eval_runs.append(_run(ctx, case))
    ctx.risk_treatments.append(
        RiskTreatment(
            session_id=ctx.session_id,
            source_type="failure_mode",
            source_id="FM-001",
            risk_level="high",
            owner="owner-a",
            mitigation_plan="plan",
            status="completed",
        )
    )
    ctx.project_approvals.append(
        ProjectApproval(
            session_id=ctx.session_id,
            status="approved",
            evaluation_version_digest=before,
        )
    )

    assert current_evaluation_digest(ctx) == before


def test_policy_version_change_changes_digest():
    ctx = _ctx()
    before = current_evaluation_digest(ctx)

    original = RULE_MANIFEST["risk_treatment"]
    RULE_MANIFEST["risk_treatment"] = replace(original, version="1.1.0")
    try:
        changed = current_evaluation_digest(ctx)
        assert changed != before
    finally:
        RULE_MANIFEST["risk_treatment"] = original


def test_evaluation_version_reports_extended_coverage():
    ctx = _ctx()
    version = build_evaluation_version(ctx)
    assert version["schema"] == "2.0"
    assert version["input_versions"] == {}
    assert version["content_digest"]
