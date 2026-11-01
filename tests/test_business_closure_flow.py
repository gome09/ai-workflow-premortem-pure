# tests/test_business_closure_flow.py
"""End-to-end business closure through the SessionService facade."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.evaluation_version import current_evaluation_digest, eval_case_digest
from core.models import (
    EvalCase,
    EvalExperiment,
    EvalRun,
    EvidenceSource,
    FailureMode,
    HumanOversightPolicy,
    ProjectContext,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
    TargetDeployment,
    TriggerMethod,
    WorkflowNode,
)
from core.risk.models import RiskFactorScores
from core.risk_treatment_service import review_risk_treatment, upsert_risk_treatment
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "closure-tenant"
_CREATOR = "creator-user"
_ADMIN = "independent-admin"


def _complete_ctx() -> ProjectContext:
    ctx = ProjectContext(
        tenant_id=_TENANT,
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        created_by=_CREATOR,
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.COMPLETE
    ctx.risk_profile = RiskFactorScores(
        impact=0,
        autonomy=0,
        data_sensitivity=1,
        reversibility=0,
        scale=0,
        external_exposure=0,
        rationale="low risk framing",
        source="human",
    )
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
                severity="high",
                evidence_ids=["EVID-1"],
            )
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-1",
                stage_name="Answer",
                model_assigned="model",
                human_action="review",
                check_criteria="citations",
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
    case = EvalCase(
        session_id=ctx.session_id,
        stage_id=3,
        target_node_id="N-1",
        scenario_type="normal",
        input_payload="policy question",
        expected_behavior="answer with citation",
        pass_criteria=["citation present"],
        passed=True,
    )
    ctx.eval_cases.append(case)
    ctx.stage_output_versions = {"stage_1": 1, "stage_2": 1, "stage_3": 1, "stage_4": 1}
    ctx.target_deployment = TargetDeployment(
        endpoint="http://target.local/eval",
        version="2026.11.1",
        updated_by=_CREATOR,
    )
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
        note="verified",
        actor_id="reviewer-b",
        actor_role="editor",
    )
    return ctx


@pytest.fixture
def service(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "closure.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService(), store, cache


def test_complete_business_closure_flow(service):
    svc, store, _cache = service
    ctx = _complete_ctx()
    store.save(ctx)

    status = svc.get_approval_status(ctx.session_id, tenant_id=_TENANT)
    assert status["release_readiness"]["can_approve"] is True
    assert status["approval_summary"]["is_release_approved"] is False

    result = svc.request_release_approval(
        ctx.session_id,
        decision="approve",
        note="independent release sign-off",
        actor_id=_ADMIN,
        actor_role="admin",
        tenant_id=_TENANT,
    )
    assert result["approval"]["status"] == "approved"
    assert result["approval_summary"]["is_release_approved"] is True

    report = svc.export_report(ctx.session_id, format="json", tenant_id=_TENANT)
    assert report["approval_summary"]["is_release_approved"] is True
    assert report["approval_summary"]["report_generation"]["is_approval"] is False


def test_content_change_invalidates_test_and_approval(service):
    svc, store, cache = service
    ctx = _complete_ctx()
    store.save(ctx)
    svc.request_release_approval(
        ctx.session_id,
        decision="approve",
        note="approved",
        actor_id=_ADMIN,
        actor_role="admin",
        tenant_id=_TENANT,
    )

    reloaded = svc.get_session(ctx.session_id, tenant_id=_TENANT)
    assert reloaded is not None
    reloaded.stage_1_output.failure_modes[0].category = "changed category"
    store.save(reloaded)
    cache.set(reloaded)

    status = svc.get_approval_status(ctx.session_id, tenant_id=_TENANT)
    assert status["approval_summary"]["release_approval"]["status"] == "stale"
    assert status["approval_summary"]["is_release_approved"] is False
    assert status["release_readiness"]["passed_real_test_node_ids"] == []


def test_risk_treatment_listing_is_exposed(service):
    svc, store, _cache = service
    ctx = _complete_ctx()
    store.save(ctx)

    payload = svc.list_risk_treatments(ctx.session_id, tenant_id=_TENANT)
    assert payload["applicable"] is True
    assert payload["summary"]["requirements_total"] == 1
    assert payload["summary"]["complete_count"] == 1
