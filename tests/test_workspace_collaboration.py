"""Real auth/API collaboration flow: workspace invite, independence, refresh role."""

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
from core.target_testing import TargetTestResponse
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TARGET_ENDPOINT = "http://target.local/eval"
_TARGET_VERSION = "2026.11.1"


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

    store = SQLiteSessionStore(str(tmp_path / "workspace_collaboration.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
        patch("auth.service.session_store", store),
    ):
        from api.main import app

        yield TestClient(app), store, cache


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _complete_context(
    store: SQLiteSessionStore,
    cache: MemoryCache,
    *,
    session_id: str,
    tenant_id: str,
    author_id: str,
    reviewer_id: str,
    with_treatment: bool = True,
) -> tuple[ProjectContext, EvalRun]:
    ctx = store.load(session_id, tenant_id)
    assert ctx is not None
    assert ctx.created_by == author_id
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
    ctx.target_deployment = TargetDeployment(
        endpoint=_TARGET_ENDPOINT,
        version=_TARGET_VERSION,
        updated_by=author_id,
    )
    ctx.evidence_sources.append(
        EvidenceSource(
            evidence_id="EVID-1",
            session_id=ctx.session_id,
            title="Policy test report",
            source_type="official_doc",
            credibility_score=0.9,
            verified=True,
            verified_by=reviewer_id,
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
    digest = current_evaluation_digest(ctx)
    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        target_node_id="N-1",
        run_mode="target_http",
        execution_kind="real_target_execution",
        execution_outcome="success",
        evaluation_version_digest=digest,
        target_endpoint=_TARGET_ENDPOINT,
        target_deployment_version=_TARGET_VERSION,
        case_version_digest=eval_case_digest(case),
        input_payload=case.input_payload,
        expected_behavior=case.expected_behavior,
        pass_criteria=list(case.pass_criteria),
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
        owner=author_id,
        mitigation_plan="Add citation validation",
        status="completed",
        actor_id=author_id,
        actor_role="admin",
    )
    if with_treatment:
        review_risk_treatment(
            ctx,
            treatment_id=treatment.treatment_id,
            decision="accept",
            note="independent review",
            actor_id=reviewer_id,
            actor_role="admin",
        )
    store.save(ctx)
    cache.set(ctx)
    return ctx, run


def test_workspace_invite_approval_and_identity_rules(api_client_and_store):
    client, store, cache = api_client_and_store

    author = client.post(
        "/auth/register",
        json={"email": "author@example.com", "password": "author-pass", "workspace_name": "Team"},
    )
    assert author.status_code == 200
    author_body = author.json()
    assert author_body["role"] == "admin"

    invitation = client.post(
        "/auth/invitations",
        json={"email": "reviewer@example.com", "role": "admin"},
        headers=_headers(author_body["access_token"]),
    )
    assert invitation.status_code == 200
    invitation_body = invitation.json()
    assert invitation_body["token"]
    assert invitation_body["tenant_id"] == author_body["tenant_id"]

    accepted = client.post(
        "/auth/invitations/accept",
        json={"token": invitation_body["token"], "password": "reviewer-pass"},
    )
    assert accepted.status_code == 200
    reviewer_body = accepted.json()
    assert reviewer_body["role"] == "admin"
    assert reviewer_body["tenant_id"] == author_body["tenant_id"]

    members = client.get("/auth/users", headers=_headers(author_body["access_token"]))
    assert members.status_code == 200
    emails = {item["email"] for item in members.json()}
    assert emails == {"author@example.com", "reviewer@example.com"}

    created = client.post(
        "/sessions/",
        json={},
        headers=_headers(author_body["access_token"]),
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    _ctx, run = _complete_context(
        store,
        cache,
        session_id=session_id,
        tenant_id=author_body["tenant_id"],
        author_id=author_body["user_id"],
        reviewer_id=reviewer_body["user_id"],
    )

    approval_path = f"/sessions/{session_id}/approvals/release"
    self_approval = client.post(
        approval_path,
        json={"decision": "approve", "note": "self"},
        headers=_headers(author_body["access_token"]),
    )
    assert self_approval.status_code == 403

    other = client.post(
        "/auth/register",
        json={"email": "other@example.com", "password": "other-pass"},
    )
    assert other.status_code == 200
    other_body = other.json()
    cross_tenant = client.get(
        f"/sessions/{session_id}/approval-status",
        headers=_headers(other_body["access_token"]),
    )
    assert cross_tenant.status_code == 404

    approved = client.post(
        approval_path,
        json={"decision": "approve", "note": "independent"},
        headers=_headers(reviewer_body["access_token"]),
    )
    assert approved.status_code == 200
    assert approved.json()["approval_summary"]["is_release_approved"] is True

    forged = client.post(
        f"/sessions/{session_id}/eval-runs/{run.run_id}/calibrate",
        json={
            "human_label": "failed",
            "human_comment": "forged body reviewer",
            "reviewer_id": "forged-reviewer",
            "disagreement_reason": "test",
        },
        headers=_headers(reviewer_body["access_token"]),
    )
    assert forged.status_code == 200
    assert forged.json()["reviewer_id"] == reviewer_body["user_id"]

    downgraded = client.patch(
        f"/auth/users/{reviewer_body['user_id']}/role",
        json={"role": "viewer"},
        headers=_headers(author_body["access_token"]),
    )
    assert downgraded.status_code == 200

    refreshed = client.post(
        "/auth/refresh",
        json={"refresh_token": reviewer_body["refresh_token"]},
    )
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    assert refreshed_body["role"] == "viewer"
    assert refreshed_body["tenant_id"] == author_body["tenant_id"]

    denied = client.post(
        approval_path,
        json={"decision": "approve", "note": "downgraded"},
        headers=_headers(refreshed_body["access_token"]),
    )
    assert denied.status_code == 403


def test_case_standard_materials_and_target_version_api(api_client_and_store, monkeypatch):
    client, store, cache = api_client_and_store
    author = client.post(
        "/auth/register",
        json={"email": "lifecycle@example.com", "password": "lifecycle-pass"},
    )
    assert author.status_code == 200
    author_body = author.json()

    created = client.post("/sessions/", json={}, headers=_headers(author_body["access_token"]))
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    ctx, _old_run = _complete_context(
        store,
        cache,
        session_id=session_id,
        tenant_id=author_body["tenant_id"],
        author_id=author_body["user_id"],
        reviewer_id=author_body["user_id"],
        with_treatment=False,
    )
    case = ctx.eval_cases[0]
    headers = _headers(author_body["access_token"])

    deployment = client.put(
        f"/sessions/{session_id}/target-deployment",
        json={"endpoint": _TARGET_ENDPOINT, "version": "v2"},
        headers=headers,
    )
    assert deployment.status_code == 200
    assert deployment.json()["changed"] is True

    updated = client.patch(
        f"/sessions/{session_id}/eval-cases/{case.eval_id}",
        json={"pass_criteria": ["citation present", "no invented clause"]},
        headers=headers,
    )
    assert updated.status_code == 200, updated.json()
    assert updated.json()["standard_version"] == 2

    materials = client.post(
        f"/sessions/{session_id}/materials",
        json={"materials": ["new user material"]},
        headers=headers,
    )
    assert materials.status_code == 200

    class FakeAdapter:
        def __init__(self, config):
            self.config = config

        def execute(self, *args, **kwargs):
            return TargetTestResponse(
                outcome="success",
                output="answer with citation",
                status_code=200,
                endpoint=_TARGET_ENDPOINT,
            )

    monkeypatch.setattr("core.eval_runner.HttpJsonTargetAdapter", FakeAdapter)
    run_response = client.post(
        f"/sessions/{session_id}/eval-cases/{case.eval_id}/run",
        json={
            "run_mode": "target_http",
            "target_config": {
                "endpoint": _TARGET_ENDPOINT,
                "timeout_seconds": 5,
                "output_field": "output",
            },
        },
        headers=headers,
    )
    assert run_response.status_code == 200
    created_runs = run_response.json()["created_runs"]
    assert created_runs
    new_run = created_runs[-1]
    assert new_run["pass_criteria"] == ["citation present", "no invented clause"]
    assert new_run["target_deployment_version"] == "v2"
    assert new_run["case_version_digest"]
