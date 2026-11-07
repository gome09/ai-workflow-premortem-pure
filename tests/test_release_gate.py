"""Release gate: machine decision contract, credentials, and fail-closed paths."""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from auth.jwt import create_access_token
from auth.service_tokens import hash_service_token
from core.approval_service import request_release_approval
from core.eval_judgment_service import calibrate_eval_run
from core.evaluation_version import current_evaluation_digest, eval_case_digest
from core.models import (
    EvalCase,
    EvalExperiment,
    EvalRun,
    EvidenceSource,
    FailureMode,
    HumanOversightPolicy,
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
from core.release_gate_service import evaluate_release_gate
from core.risk.models import RiskFactorScores
from core.risk_treatment_service import review_risk_treatment, upsert_risk_treatment
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_CREATOR = "creator-user"
_REVIEWER = "reviewer-admin"
_TARGET_ENDPOINT = "http://target.local/eval"
_TARGET_VERSION = "2026.11.1"


def _approvable_context(
    *,
    tenant_id: str,
    data_classification: str = "business_internal",
) -> ProjectContext:
    ctx = ProjectContext(
        tenant_id=tenant_id,
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        created_by=_CREATOR,
        data_classification=data_classification,
    )
    ctx.current_state = SessionState.COMPLETE
    ctx.risk_profile = RiskFactorScores(
        impact=0,
        autonomy=0,
        data_sensitivity=1,
        reversibility=0,
        scale=0,
        external_exposure=0,
        rationale="low risk framing for release gate tests",
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
    ctx.stage_output_versions = {"stage_1": 1, "stage_2": 1, "stage_3": 1, "stage_4": 1}
    ctx.target_deployment = TargetDeployment(
        endpoint=_TARGET_ENDPOINT,
        version=_TARGET_VERSION,
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


def _approve(ctx: ProjectContext) -> None:
    request_release_approval(
        ctx,
        decision="approve",
        note="approved for gate tests",
        actor_id=_REVIEWER,
        actor_role="admin",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Decision semantics (no HTTP)
# ─────────────────────────────────────────────────────────────────────────────


def test_allow_requires_current_approval() -> None:
    ctx = _approvable_context(tenant_id="tenant-a")
    _approve(ctx)

    decision = evaluate_release_gate(ctx)

    assert decision.decision == "allow"
    assert decision.reason_code == "approved"
    assert decision.approval_status == "approved"
    assert decision.applicable is True
    assert decision.approval_id
    assert decision.evaluation_version_digest
    assert decision.evidence_digest
    assert decision.release_batch_id == ctx.eval_experiments[0].experiment_id
    assert decision.blockers == []


def test_not_requested_blocks() -> None:
    ctx = _approvable_context(tenant_id="tenant-a")

    decision = evaluate_release_gate(ctx)

    assert decision.decision == "block"
    assert decision.reason_code == "approval_not_requested"
    assert decision.approval_status == "not_requested"
    assert [blocker.code for blocker in decision.blockers] == ["approval_not_requested"]


def test_rejected_blocks() -> None:
    ctx = _approvable_context(tenant_id="tenant-a")
    request_release_approval(
        ctx,
        decision="reject",
        note="not ready",
        actor_id=_REVIEWER,
        actor_role="admin",
    )

    decision = evaluate_release_gate(ctx)

    assert decision.decision == "block"
    assert decision.reason_code == "approval_rejected"
    assert decision.approval_status == "rejected"


def test_stale_blocks() -> None:
    ctx = _approvable_context(tenant_id="tenant-a")
    _approve(ctx)
    ctx.input_versions["materials"] = int((ctx.input_versions or {}).get("materials", 0)) + 1

    decision = evaluate_release_gate(ctx)

    assert decision.decision == "block"
    assert decision.reason_code == "approval_stale"
    assert decision.approval_status == "stale"


def test_invalidated_blocks() -> None:
    ctx = _approvable_context(tenant_id="tenant-a")
    _approve(ctx)
    ctx.safety_findings.append(
        SafetyFinding(
            session_id=ctx.session_id,
            risk_type="prompt_injection",
            severity="high",
            location="stage_3 input",
            description="new high finding after approval",
            recommended_action="block release until reviewed",
            status="open",
        )
    )

    decision = evaluate_release_gate(ctx)

    assert decision.decision == "block"
    assert decision.reason_code == "approval_invalidated"
    assert decision.approval_status == "invalidated"


def test_public_demo_is_not_applicable() -> None:
    ctx = _approvable_context(tenant_id="tenant-a", data_classification="public_demo")

    decision = evaluate_release_gate(ctx)

    assert decision.decision == "block"
    assert decision.reason_code == "not_applicable"
    assert decision.applicable is False
    assert [blocker.code for blocker in decision.blockers] == ["not_applicable"]


# ─────────────────────────────────────────────────────────────────────────────
# API, credential and fail-closed paths
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def gate_env(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("psycopg")
    pytest.importorskip("redis")
    pytest.importorskip("langchain_core")
    pytest.importorskip("langchain_openai")
    pytest.importorskip("tavily")
    pytest.importorskip("prometheus_fastapi_instrumentator")

    from fastapi.testclient import TestClient

    db_path = str(tmp_path / "release_gate.db")
    store = SQLiteSessionStore(db_path)
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
        patch("auth.service_tokens.session_store", store),
    ):
        from api.main import app

        yield TestClient(app), store, cache, db_path


def _tenant(store: SQLiteSessionStore, name: str) -> str:
    return str(store.create_tenant(name)["tenant_id"])


def _headers(tenant_id: str, *, role: str = "admin", sub: str = "admin-user") -> dict:
    token = create_access_token({"sub": sub, "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


def _service_headers(raw_token: str) -> dict:
    return {"Authorization": f"Bearer {raw_token}"}


def _create_token(client, tenant_id: str, *, name: str = "ci") -> dict:
    response = client.post(
        "/auth/service-tokens",
        json={"name": name, "expires_in_days": 30},
        headers=_headers(tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _save_approved_session(
    store: SQLiteSessionStore,
    tenant_id: str,
    *,
    data_classification: str = "business_internal",
) -> ProjectContext:
    ctx = _approvable_context(tenant_id=tenant_id, data_classification=data_classification)
    _approve(ctx)
    store.save(ctx)
    return ctx


def test_token_create_list_revoke_and_hash_at_rest(gate_env) -> None:
    client, store, _cache, db_path = gate_env
    tenant_id = _tenant(store, "gate-token-workspace")

    create_response = client.post(
        "/auth/service-tokens",
        json={"name": "ci", "expires_in_days": 30},
        headers=_headers(tenant_id),
    )
    assert create_response.status_code == 200
    assert create_response.headers.get("cache-control") == "no-store"
    created = create_response.json()
    assert created["token"].startswith("pmgate_")
    assert created["scope"] == "release_gate:read"
    assert created["tenant_id"] == tenant_id

    listed = client.get("/auth/service-tokens", headers=_headers(tenant_id))
    assert listed.status_code == 200
    item = listed.json()[0]
    assert "token" not in item
    assert "token_hash" not in item
    assert item["token_id"] == created["token_id"]

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT token_hash FROM service_tokens WHERE token_id=?",
            (created["token_id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == hash_service_token(created["token"])
    assert row[0] != created["token"]
    assert len(row[0]) == 64

    revoked = client.delete(
        f"/auth/service-tokens/{created['token_id']}",
        headers=_headers(tenant_id),
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"]

    response = client.get(
        "/release-gate/nonexistent-session",
        headers=_service_headers(created["token"]),
    )
    assert response.status_code == 401


def test_token_create_requires_admin(gate_env) -> None:
    client, store, _cache, _db_path = gate_env
    tenant_id = _tenant(store, "gate-editor-workspace")

    response = client.post(
        "/auth/service-tokens",
        json={"name": "ci"},
        headers=_headers(tenant_id, role="editor", sub="editor-user"),
    )

    assert response.status_code == 403


def test_gate_rejects_human_jwt(gate_env) -> None:
    client, store, _cache, _db_path = gate_env
    tenant_id = _tenant(store, "gate-human-workspace")
    ctx = _save_approved_session(store, tenant_id)

    response = client.get(
        f"/release-gate/{ctx.session_id}",
        headers=_headers(tenant_id),
    )

    assert response.status_code == 401


def test_gate_missing_or_malformed_token(gate_env) -> None:
    client, store, _cache, _db_path = gate_env
    tenant_id = _tenant(store, "gate-missing-workspace")
    ctx = _save_approved_session(store, tenant_id)

    assert client.get(f"/release-gate/{ctx.session_id}").status_code == 401

    malformed = client.get(
        f"/release-gate/{ctx.session_id}",
        headers={"Authorization": "Bearer not-a-service-token"},
    )
    assert malformed.status_code == 401


def test_gate_cross_tenant_returns_404(gate_env) -> None:
    client, store, _cache, _db_path = gate_env
    tenant_a = _tenant(store, "gate-tenant-a")
    tenant_b = _tenant(store, "gate-tenant-b")
    ctx_b = _save_approved_session(store, tenant_b)
    token_a = _create_token(client, tenant_a)

    response = client.get(
        f"/release-gate/{ctx_b.session_id}",
        headers=_service_headers(token_a["token"]),
    )

    assert response.status_code == 404


def test_gate_expired_token_returns_401(gate_env) -> None:
    client, store, _cache, _db_path = gate_env
    tenant_id = _tenant(store, "gate-expired-workspace")
    ctx = _save_approved_session(store, tenant_id)
    raw_token = f"pmgate_{secrets.token_urlsafe(32)}"
    store.create_service_token(
        token_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name="expired",
        token_hash=hash_service_token(raw_token),
        scope="release_gate:read",
        created_by="admin-user",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    response = client.get(
        f"/release-gate/{ctx.session_id}",
        headers=_service_headers(raw_token),
    )

    assert response.status_code == 401


def test_gate_response_no_store_and_check_id(gate_env) -> None:
    client, store, _cache, _db_path = gate_env
    tenant_id = _tenant(store, "gate-allow-workspace")
    ctx = _save_approved_session(store, tenant_id)
    created = _create_token(client, tenant_id)

    response = client.get(
        f"/release-gate/{ctx.session_id}",
        headers=_service_headers(created["token"]),
    )

    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert body["decision"] == "allow"
    assert body["reason_code"] == "approved"
    assert body["approval_status"] == "approved"
    assert body["check_id"]
    assert body["evaluation_version_digest"]
    assert body["evidence_digest"]


def test_gate_audit_row_written(gate_env) -> None:
    client, store, _cache, db_path = gate_env
    tenant_id = _tenant(store, "gate-audit-workspace")
    ctx = _save_approved_session(store, tenant_id)
    created = _create_token(client, tenant_id)

    response = client.get(
        f"/release-gate/{ctx.session_id}",
        headers=_service_headers(created["token"]),
    )
    assert response.status_code == 200
    body = response.json()

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT decision, reason_code, approval_status, approval_id, "
            "evaluation_version_digest, evidence_digest, release_batch_id, tenant_id, token_id "
            "FROM release_gate_checks WHERE check_id=?",
            (body["check_id"],),
        ).fetchone()

    assert row is not None
    assert row[0] == "allow"
    assert row[1] == "approved"
    assert row[2] == "approved"
    assert row[3] == body["approval_id"]
    assert row[4] == body["evaluation_version_digest"]
    assert row[5] == body["evidence_digest"]
    assert row[6] == body["release_batch_id"]
    assert row[7] == tenant_id
    assert row[8] == created["token_id"]


def test_gate_audit_failure_is_fail_closed(gate_env) -> None:
    client, store, _cache, _db_path = gate_env
    tenant_id = _tenant(store, "gate-fail-closed-workspace")
    ctx = _save_approved_session(store, tenant_id)
    created = _create_token(client, tenant_id)

    with patch.object(store, "record_release_gate_check", side_effect=RuntimeError("boom")):
        response = client.get(
            f"/release-gate/{ctx.session_id}",
            headers=_service_headers(created["token"]),
        )

    assert response.status_code == 503
    body = response.json()
    assert body["decision"] == "block"
    assert body["reason_code"] == "gate_unavailable"
    assert response.headers.get("cache-control") == "no-store"


def test_gate_bypasses_context_cache(gate_env) -> None:
    client, store, cache, _db_path = gate_env
    tenant_id = _tenant(store, "gate-cache-workspace")
    approved = _save_approved_session(store, tenant_id)
    cache.set(approved)

    fresh = store.load(approved.session_id, tenant_id)
    assert fresh is not None
    fresh.safety_findings.append(
        SafetyFinding(
            session_id=fresh.session_id,
            risk_type="prompt_injection",
            severity="high",
            location="stage_3 input",
            description="new high finding after approval",
            recommended_action="block release until reviewed",
            status="open",
        )
    )
    store.save(fresh)

    created = _create_token(client, tenant_id)
    response = client.get(
        f"/release-gate/{fresh.session_id}",
        headers=_service_headers(created["token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "block"
    assert body["reason_code"] == "approval_invalidated"
