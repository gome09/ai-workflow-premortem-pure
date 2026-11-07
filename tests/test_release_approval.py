# tests/test_release_approval.py
"""Independent release approval: prerequisites, identity, and version binding."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core import eval_runner
from core.approval_service import (
    ReleaseApprovalAuthorizationError,
    ReleaseApprovalNotApplicableError,
    ReleaseApprovalPrerequisiteError,
    build_approval_summary,
    build_release_readiness,
    request_release_approval,
)
from core.eval_judgment_service import calibrate_eval_run
from core.eval_runner import run_eval_case
from core.evaluation_version import current_evaluation_digest, eval_case_digest
from core.models import (
    EvalCase,
    EvalExperiment,
    EvalRun,
    EvidenceSource,
    FailureMode,
    HumanOversightPolicy,
    PendingHumanAction,
    ProjectApproval,
    ProjectContext,
    SafetyFinding,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
    TargetDeployment,
    TriggerMethod,
    WorkflowNode,
)
from core.report_service import build_report_dict, create_report_artifact
from core.risk.models import RiskFactorScores
from core.risk_treatment_service import (
    review_risk_treatment,
    upsert_risk_treatment,
)
from core.target_testing import TargetSystemConfig, TargetTestResponse
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "test-tenant"
_CREATOR = "creator-user"
_REVIEWER = "reviewer-admin"

_LOW_RISK = RiskFactorScores(
    impact=0,
    autonomy=0,
    data_sensitivity=1,
    reversibility=0,
    scale=0,
    external_exposure=0,
    rationale="low risk framing for release approval tests",
    source="human",
)


def _ctx(
    *,
    data_classification: str = "business_internal",
    with_treatment: bool = True,
    failure_mode_severity: str = "high",
) -> ProjectContext:
    ctx = ProjectContext(
        tenant_id=_TENANT,
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        created_by=_CREATOR,
        data_classification=data_classification,
    )
    ctx.current_state = SessionState.COMPLETE
    ctx.risk_profile = _LOW_RISK
    ctx.evidence_sources.append(
        EvidenceSource(
            evidence_id="EVID-1",
            session_id=ctx.session_id,
            title="Policy test report",
            source_type="official_doc",
            credibility_score=0.9,
            verified=True,
            verified_by="reviewer",
        )
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="hallucination",
                description="Invents policy clauses",
                severity=failure_mode_severity,
                evidence_ids=["EVID-1"],
            )
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-1",
                stage_name="Answer generation",
                model_assigned="model",
                human_action="Review answer",
                check_criteria="Citations exist",
                failure_modes_addressed=["FM-001"],
                prompt_template="answer",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="low",
                    trigger_reason="low risk",
                    required_action="approve",
                    can_auto_continue=True,
                ),
            )
        ]
    )
    ctx.stage_3_output = Stage3Output(test_results=[])
    ctx.stage_4_output = Stage4Output(
        trigger_methods=[
            TriggerMethod(
                node_id="N-1",
                model_or_mode="model",
                entry_point="chat",
                trigger_instruction="ask",
                execution_suggestion="run",
            )
        ]
    )
    ctx.eval_cases.append(
        EvalCase(
            session_id=ctx.session_id,
            stage_id=3,
            target_node_id="N-1",
            scenario_type="normal",
            input_payload="policy question",
            expected_behavior="answer with citation",
            pass_criteria=["citation present"],
            passed=True,
        )
    )
    ctx.stage_output_versions = {
        "stage_1": 1,
        "stage_2": 1,
        "stage_3": 1,
        "stage_4": 1,
    }
    ctx.target_deployment = TargetDeployment(
        endpoint="http://target.local/eval",
        version="2026.11.1",
        updated_by=_CREATOR,
    )
    case = ctx.eval_cases[0]
    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        target_node_id="N-1",
        run_mode="target_http",
        execution_kind="real_target_execution",
        execution_outcome="success",
        evaluation_version_digest=current_evaluation_digest(ctx),
        target_endpoint=ctx.target_deployment.endpoint,
        target_deployment_version=ctx.target_deployment.version,
        case_version_digest=eval_case_digest(case),
        input_payload="policy question",
        expected_behavior="answer with citation",
        pass_criteria=["citation present"],
        actual_output="answer with citation",
        judge_result="passed",
        status="completed",
    )
    ctx.eval_runs.append(run)
    calibrate_eval_run(
        ctx,
        eval_run_id=run.run_id,
        human_label="passed",
        human_comment="人工核对实际输出，包含 pass_criteria 要求的 citation。",
        reviewer_id="reviewer-b",
        actor_role="editor",
    )
    ctx.eval_experiments.append(
        EvalExperiment(
            session_id=ctx.session_id,
            dataset_id="ds-test",
            name="release batch",
            status="completed",
            run_mode="target_http",
            eval_ids=[case.eval_id],
            run_ids=[run.run_id],
        )
    )
    if with_treatment:
        treatment = upsert_risk_treatment(
            ctx,
            source_type="failure_mode",
            source_id="FM-001",
            owner="owner-a",
            mitigation_plan="Add citation validation",
            status="completed",
            actor_id="editor-a",
            actor_role="editor",
        )
        review_risk_treatment(
            ctx,
            treatment_id=treatment.treatment_id,
            decision="accept",
            note="verified mitigation",
            actor_id="reviewer-b",
            actor_role="editor",
        )
    return ctx


def test_report_generation_does_not_create_approval():
    ctx = _ctx()
    report = build_report_dict(ctx)
    artifact = create_report_artifact(ctx)

    summary = report["approval_summary"]
    assert summary["report_generation"]["is_approval"] is False
    assert summary["release_approval"]["status"] == "not_requested"
    assert summary["is_release_approved"] is False
    assert report["report_export_status"]["is_approval"] is False
    assert "不代表上线批准" in artifact.content_markdown


def test_evaluation_not_completed_blocks_approval():
    ctx = _ctx()
    ctx.current_state = SessionState.S4_REVIEW

    with pytest.raises(ReleaseApprovalPrerequisiteError) as exc:
        request_release_approval(
            ctx,
            decision="approve",
            note="",
            actor_id=_REVIEWER,
            actor_role="admin",
        )

    assert [blocker.code for blocker in exc.value.blockers] == ["evaluation_not_completed"]


def test_missing_real_target_test_blocks_approval():
    ctx = _ctx()
    ctx.eval_runs = []

    with pytest.raises(ReleaseApprovalPrerequisiteError) as exc:
        request_release_approval(
            ctx,
            decision="approve",
            note="",
            actor_id=_REVIEWER,
            actor_role="admin",
        )

    assert any(blocker.code == "real_target_test" for blocker in exc.value.blockers)


def test_missing_treatment_blocks_approval():
    ctx = _ctx(with_treatment=False)

    with pytest.raises(ReleaseApprovalPrerequisiteError) as exc:
        request_release_approval(
            ctx,
            decision="approve",
            note="",
            actor_id=_REVIEWER,
            actor_role="admin",
        )

    assert any(blocker.code == "risk_treatment" for blocker in exc.value.blockers)


def test_simulation_run_does_not_count_as_real_test():
    ctx = _ctx()
    ctx.eval_runs[0].execution_kind = "manual_simulation"
    ctx.eval_runs[0].run_mode = "manual"

    readiness = build_release_readiness(ctx)

    assert readiness.checks["real_target_tests_passed"] is False
    assert any(blocker.code == "real_target_test" for blocker in readiness.blockers)


def test_requires_admin_and_independent_reviewer():
    ctx = _ctx()
    with pytest.raises(ReleaseApprovalAuthorizationError, match="admin role"):
        request_release_approval(
            ctx,
            decision="approve",
            note="",
            actor_id="editor-user",
            actor_role="editor",
        )

    with pytest.raises(ReleaseApprovalAuthorizationError, match="Self-approval"):
        request_release_approval(
            ctx,
            decision="approve",
            note="",
            actor_id=_CREATOR,
            actor_role="admin",
        )

    with pytest.raises(ReleaseApprovalAuthorizationError, match="creator is not recorded"):
        ctx.created_by = ""
        request_release_approval(
            ctx,
            decision="approve",
            note="",
            actor_id=_REVIEWER,
            actor_role="admin",
        )


def test_valid_admin_approval_records_digest():
    ctx = _ctx()
    approval, readiness, replayed = request_release_approval(
        ctx,
        decision="approve",
        note="independent release approval",
        actor_id=_REVIEWER,
        actor_role="admin",
    )

    assert replayed is False
    assert readiness.can_approve is True
    assert approval.status == "approved"
    assert approval.decided_by == _REVIEWER
    assert approval.evaluation_version_digest == current_evaluation_digest(ctx)

    event = next(
        item for item in reversed(ctx.audit_events) if item.event_type == "release_approval_granted"
    )
    assert event.metadata["reviewer_id"] == _REVIEWER
    assert event.metadata["evaluation_version_digest"] == approval.evaluation_version_digest
    assert build_approval_summary(ctx)["is_release_approved"] is True


def test_replay_is_idempotent_when_prerequisites_still_hold():
    ctx = _ctx()
    first, _, _ = request_release_approval(
        ctx,
        decision="approve",
        note="first",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    second, _, replayed = request_release_approval(
        ctx,
        decision="approve",
        note="second",
        actor_id=_REVIEWER,
        actor_role="admin",
    )

    assert replayed is True
    assert second.approval_id == first.approval_id
    assert len(ctx.project_approvals) == 1


def test_content_change_makes_approval_stale():
    ctx = _ctx()
    approval, _, _ = request_release_approval(
        ctx,
        decision="approve",
        note="approved",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert build_approval_summary(ctx)["is_release_approved"] is True

    ctx.stage_1_output.failure_modes[0].category = "changed hallucination category"

    summary = build_approval_summary(ctx)
    assert summary["release_approval"]["status"] == "stale"
    assert summary["release_approval"]["stale_reason"]
    assert summary["is_release_approved"] is False
    assert len(ctx.project_approvals) == 1
    assert ctx.project_approvals[0].approval_id == approval.approval_id


def test_public_demo_is_not_applicable():
    ctx = _ctx(data_classification="public_demo")

    with pytest.raises(ReleaseApprovalNotApplicableError):
        request_release_approval(
            ctx,
            decision="approve",
            note="",
            actor_id=_REVIEWER,
            actor_role="admin",
        )

    readiness = build_release_readiness(ctx)
    assert readiness.applicable is False
    assert readiness.exempt_reason == "public_demo"


def _approve(ctx: ProjectContext) -> ProjectApproval:
    approval, _, _ = request_release_approval(
        ctx,
        decision="approve",
        note="baseline approval",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert build_approval_summary(ctx)["is_release_approved"] is True
    return approval


def test_treatment_rejection_invalidates_approval_but_keeps_history():
    ctx = _ctx()
    approval = _approve(ctx)

    review_risk_treatment(
        ctx,
        treatment_id=ctx.risk_treatments[0].treatment_id,
        decision="reject",
        note="mitigation rejected",
        actor_id="reviewer-b",
        actor_role="editor",
    )

    summary = build_approval_summary(ctx)
    assert summary["release_approval"]["status"] == "invalidated"
    assert summary["release_approval"]["invalidated_reason"]
    assert summary["is_release_approved"] is False
    assert summary["history_count"] == 1
    assert ctx.project_approvals[0].approval_id == approval.approval_id


def test_test_rejudgment_invalidates_approval():
    ctx = _ctx()
    _approve(ctx)

    calibrate_eval_run(
        ctx,
        eval_run_id=ctx.eval_runs[0].run_id,
        human_label="failed",
        human_comment="semantic re-judgment",
        reviewer_id="reviewer-b",
    )

    summary = build_approval_summary(ctx)
    assert summary["release_approval"]["status"] == "invalidated"
    assert summary["is_release_approved"] is False
    assert summary["history_count"] == 1


def test_new_high_safety_finding_invalidates_approval():
    ctx = _ctx()
    _approve(ctx)

    ctx.safety_findings.append(
        SafetyFinding(
            session_id=ctx.session_id,
            stage_id=3,
            risk_type="unsupported_claim",
            severity="high",
            location="stage_3",
            description="New high-severity safety finding",
            recommended_action="resolve",
            requires_human_review=True,
        )
    )

    summary = build_approval_summary(ctx)
    assert summary["release_approval"]["status"] == "invalidated"
    assert summary["is_release_approved"] is False
    assert summary["history_count"] == 1


def test_invalidated_approval_does_not_revive_and_new_approval_appends():
    ctx = _ctx()
    _approve(ctx)
    treatment = ctx.risk_treatments[0]

    review_risk_treatment(
        ctx,
        treatment_id=treatment.treatment_id,
        decision="reject",
        note="reject",
        actor_id="reviewer-b",
        actor_role="editor",
    )
    upsert_risk_treatment(
        ctx,
        source_type="failure_mode",
        source_id="FM-001",
        owner=treatment.owner,
        mitigation_plan=treatment.mitigation_plan,
        status="completed",
        actor_id="editor-a",
        actor_role="editor",
    )
    review_risk_treatment(
        ctx,
        treatment_id=treatment.treatment_id,
        decision="accept",
        note="re-accepted",
        actor_id="reviewer-b",
        actor_role="editor",
    )

    summary = build_approval_summary(ctx)
    assert summary["release_approval"]["status"] == "invalidated"
    assert summary["history_count"] == 1

    _second, _, replayed = request_release_approval(
        ctx,
        decision="approve",
        note="fresh approval after evidence change",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert replayed is False
    assert summary["history_count"] == 1
    summary_after = build_approval_summary(ctx)
    assert summary_after["release_approval"]["status"] == "approved"
    assert summary_after["history_count"] == 2


def test_failed_target_execution_is_not_release_evidence_even_if_marked_passed():
    ctx = _ctx()
    run = ctx.eval_runs[0]
    run.execution_outcome = "failed"
    run.judge_result = "passed"

    readiness = build_release_readiness(ctx)
    assert readiness.checks["real_target_tests_passed"] is False
    assert any(blocker.code == "real_target_test" for blocker in readiness.blockers)

    with pytest.raises(ValueError, match="cannot be calibrated to passed"):
        calibrate_eval_run(
            ctx,
            eval_run_id=run.run_id,
            human_label="passed",
            reviewer_id="reviewer-b",
        )


def test_release_batch_requires_all_required_cases():
    ctx = _ctx()
    ctx.eval_experiments[0].run_ids = []

    readiness = build_release_readiness(ctx)

    assert readiness.checks["release_batch_complete"] is False
    assert any(blocker.code == "real_target_test" for blocker in readiness.blockers)


def test_required_test_failure_blocks_release():
    ctx = _ctx()
    ctx.eval_runs[0].judge_result = "failed"

    readiness = build_release_readiness(ctx)

    assert readiness.checks["real_target_tests_passed"] is False
    assert any(blocker.code == "real_target_test" for blocker in readiness.blockers)


def test_missing_target_deployment_blocks_release():
    ctx = _ctx()
    ctx.target_deployment = None

    readiness = build_release_readiness(ctx)

    assert readiness.checks["target_deployment_declared"] is False
    assert any(blocker.code == "target_deployment" for blocker in readiness.blockers)


def test_uncalibrated_passed_run_is_not_release_evidence():
    ctx = _ctx()
    ctx.human_calibrations.clear()
    ctx.eval_runs[0].judge_mode = "rule"

    readiness = build_release_readiness(ctx)

    assert readiness.checks["real_target_tests_passed"] is False
    assert any(blocker.code == "real_target_test" for blocker in readiness.blockers)


def test_human_review_without_written_basis_is_not_release_evidence():
    ctx = _ctx()
    ctx.human_calibrations[0].human_comment = ""

    readiness = build_release_readiness(ctx)

    assert readiness.checks["real_target_tests_passed"] is False
    assert any(blocker.code == "real_target_test" for blocker in readiness.blockers)


def test_calibrate_passed_requires_written_basis():
    ctx = _ctx()

    with pytest.raises(ValueError, match="written judgment basis"):
        calibrate_eval_run(
            ctx,
            eval_run_id=ctx.eval_runs[0].run_id,
            human_label="passed",
            human_comment="",
            reviewer_id="reviewer-b",
            actor_role="editor",
        )


def test_calibration_closes_pending_eval_run_action_and_allows_approval():
    ctx = _ctx()
    run = ctx.eval_runs[0]
    action = PendingHumanAction(
        session_id=ctx.session_id,
        stage_id=3,
        source_type="eval_run",
        source_id=run.run_id,
        action_type="edit",
        title="Review required eval run",
        description="legacy eval review action",
        risk_level="high",
        blocking=True,
        stage_output_version=1,
    )
    ctx.pending_actions.append(action)

    assert not build_release_readiness(ctx).can_approve

    calibrate_eval_run(
        ctx,
        eval_run_id=run.run_id,
        human_label="passed",
        human_comment="人工复核通过，实际输出满足 pass_criteria。",
        reviewer_id="reviewer-b",
        actor_role="editor",
    )

    assert action.status == "resolved"
    assert action.reviewer_decision == "approve"
    readiness = build_release_readiness(ctx)
    assert readiness.can_approve is True

    approval, _, _ = request_release_approval(
        ctx,
        decision="approve",
        note="independent approval after human review",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert approval.status == "approved"


def test_actual_output_change_invalidates_approval():
    ctx = _ctx()
    approval, _, _ = request_release_approval(
        ctx,
        decision="approve",
        note="approved",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert build_approval_summary(ctx)["is_release_approved"] is True

    ctx.eval_runs[0].actual_output = "tampered output"

    summary = build_approval_summary(ctx)
    assert summary["release_approval"]["status"] == "invalidated"
    assert summary["is_release_approved"] is False
    assert len(ctx.project_approvals) == 1
    assert ctx.project_approvals[0].approval_id == approval.approval_id


def test_human_comment_change_invalidates_approval():
    ctx = _ctx()
    _approve(ctx)

    ctx.human_calibrations[0].human_comment = "different judgment basis"

    summary = build_approval_summary(ctx)
    assert summary["release_approval"]["status"] == "invalidated"
    assert summary["is_release_approved"] is False


def test_real_target_run_review_and_approval_end_to_end(monkeypatch):
    ctx = _ctx(failure_mode_severity="critical")
    ctx.eval_runs.clear()
    ctx.eval_experiments.clear()
    ctx.human_calibrations.clear()
    case = ctx.eval_cases[0]

    class FakeAdapter:
        def __init__(self, config):
            self.config = config

        def execute(self, *args, **kwargs):
            return TargetTestResponse(
                outcome="success",
                output="answer with citation",
                status_code=200,
            )

    monkeypatch.setattr(eval_runner, "HttpJsonTargetAdapter", FakeAdapter)

    run = run_eval_case(
        ctx,
        eval_id=case.eval_id,
        run_mode="target_http",
        target_config=TargetSystemConfig(endpoint=ctx.target_deployment.endpoint),
    )
    assert run.judge_result == "needs_review"
    action = next(
        item
        for item in ctx.pending_actions
        if item.source_type == "eval_run" and item.source_id == run.run_id
    )
    assert action.blocking is True
    assert action.action_type == "approve"

    calibrate_eval_run(
        ctx,
        eval_run_id=run.run_id,
        human_label="passed",
        human_comment="人工核对实际输出，包含 pass_criteria 要求的 citation。",
        reviewer_id="reviewer-b",
        actor_role="editor",
    )
    assert action.status == "resolved"
    assert run.judge_mode == "human"
    assert run.judge_result == "passed"

    ctx.eval_experiments.append(
        EvalExperiment(
            session_id=ctx.session_id,
            dataset_id="ds-test",
            name="release batch",
            status="completed",
            run_mode="target_http",
            eval_ids=[case.eval_id],
            run_ids=[run.run_id],
        )
    )

    readiness = build_release_readiness(ctx)
    assert readiness.can_approve is True

    approval, _, _ = request_release_approval(
        ctx,
        decision="approve",
        note="independent release sign-off",
        actor_id=_REVIEWER,
        actor_role="admin",
    )
    assert approval.status == "approved"
    assert build_approval_summary(ctx)["is_release_approved"] is True


@pytest.fixture
def api_client_and_store(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("psycopg")
    pytest.importorskip("redis")
    pytest.importorskip("langchain_core")
    pytest.importorskip("langchain_openai")
    pytest.importorskip("tavily")
    pytest.importorskip("prometheus_fastapi_instrumentator")

    from fastapi.testclient import TestClient

    from storage.backends.memory_cache import MemoryCache

    store = SQLiteSessionStore(str(tmp_path / "release_approval_api.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        from api.main import app

        yield TestClient(app), store


def _headers(role: str, sub: str, tenant_id: str = _TENANT) -> dict:
    from auth.jwt import create_access_token

    token = create_access_token({"sub": sub, "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


def test_api_approval_authorization_and_success(api_client_and_store):
    client, store = api_client_and_store
    ctx = _ctx()
    store.save(ctx)

    path = f"/sessions/{ctx.session_id}/approvals/release"

    response = client.post(
        path,
        json={"decision": "approve", "note": "editor"},
        headers=_headers("editor", "editor-user"),
    )
    assert response.status_code == 403

    response = client.post(
        path, json={"decision": "approve", "note": "self"}, headers=_headers("admin", _CREATOR)
    )
    assert response.status_code == 403

    response = client.post(
        path,
        json={"decision": "approve", "note": "cross tenant"},
        headers=_headers("admin", "other-admin", tenant_id="other-tenant"),
    )
    assert response.status_code == 404

    response = client.post(
        path,
        json={"decision": "approve", "note": "independent"},
        headers=_headers("admin", _REVIEWER),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["approval"]["status"] == "approved"
    assert payload["approval_summary"]["is_release_approved"] is True

    status_response = client.get(
        f"/sessions/{ctx.session_id}/approval-status", headers=_headers("viewer", "viewer-user")
    )
    assert status_response.status_code == 200
    assert status_response.json()["approval_summary"]["is_release_approved"] is True


def test_api_reports_do_not_grant_approval(api_client_and_store):
    client, store = api_client_and_store
    ctx = _ctx()
    store.save(ctx)

    response = client.post(
        f"/sessions/{ctx.session_id}/reports", headers=_headers("editor", "editor-user")
    )
    assert response.status_code == 200

    status_response = client.get(
        f"/sessions/{ctx.session_id}/approval-status", headers=_headers("viewer", "viewer-user")
    )
    summary = status_response.json()["approval_summary"]
    assert summary["release_approval"]["status"] == "not_requested"
    assert summary["is_release_approved"] is False
