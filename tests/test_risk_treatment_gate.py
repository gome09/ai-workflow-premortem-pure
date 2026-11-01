# tests/test_risk_treatment_gate.py
"""Risk treatment coverage and Stage 4 gate."""

from __future__ import annotations

import pytest

from core.gates.engine import evaluate_stage_gate
from core.models import (
    EvalCase,
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
    TriggerMethod,
    WorkflowNode,
)
from core.risk.models import RiskFactorScores
from core.risk_treatment_service import (
    RiskTreatmentAuthorizationError,
    RiskTreatmentStaleError,
    review_risk_treatment,
    treatment_blockers,
    upsert_risk_treatment,
)
from core.stage_resolution_service import build_stage_resolution_operations
from storage.backends.sqlite_store import SQLiteSessionStore


@pytest.fixture
def gate_store(tmp_path, monkeypatch):
    store = SQLiteSessionStore(str(tmp_path / "treatments.db"))
    store.initialize()
    monkeypatch.setattr("storage.session_store.session_store", store)
    return store


_LOW_RISK = RiskFactorScores(
    impact=0,
    autonomy=0,
    data_sensitivity=1,
    reversibility=0,
    scale=0,
    external_exposure=0,
    rationale="low risk framing for gate isolation",
    source="human",
)


def _ctx(*, data_classification: str = "business_internal") -> ProjectContext:
    ctx = ProjectContext(
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        created_by="creator-user",
        data_classification=data_classification,
    )
    ctx.current_state = SessionState.S4_REVIEW
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
    ctx.stage_output_versions = {
        "stage_1": 1,
        "stage_2": 1,
        "stage_3": 1,
        "stage_4": 1,
    }
    return ctx


def _risk_treatment_blockers(ctx: ProjectContext) -> list:
    return [
        blocker
        for blocker in evaluate_stage_gate(ctx, 4).blockers
        if blocker.blocker_type == "risk_treatment"
    ]


def test_missing_treatment_blocks_stage4(gate_store):
    ctx = _ctx()
    gate_store.save(ctx)

    blockers = _risk_treatment_blockers(ctx)

    assert len(blockers) == 1
    assert blockers[0].rule_id == "risk_treatment"
    assert blockers[0].can_be_overridden_by_approval is False
    assert blockers[0].required_resolution == "complete_risk_treatment"
    assert blockers[0].metadata["gap_type"] == "missing"


def test_planned_or_unreviewed_treatment_still_blocks(gate_store):
    ctx = _ctx()
    gate_store.save(ctx)
    treatment = upsert_risk_treatment(
        ctx,
        source_type="failure_mode",
        source_id="FM-001",
        owner="owner-a",
        mitigation_plan="Add citation validation",
        status="planned",
        actor_id="editor-a",
        actor_role="editor",
    )
    assert treatment_blockers(ctx)[0]["gap_type"] == "not_final"

    treatment.status = "completed"
    treatment.updated_by = "editor-b"
    assert treatment_blockers(ctx)[0]["gap_type"] == "unreviewed"


def test_reviewed_completed_treatment_unblocks(gate_store):
    ctx = _ctx()
    gate_store.save(ctx)
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
    gate_store.save(ctx)

    assert treatment_blockers(ctx) == []
    assert _risk_treatment_blockers(ctx) == []


def test_content_change_makes_treatment_stale(gate_store):
    ctx = _ctx()
    gate_store.save(ctx)
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
        note="ok",
        actor_id="reviewer-b",
        actor_role="editor",
    )
    assert treatment_blockers(ctx) == []

    ctx.stage_1_output.failure_modes[0].category = "updated hallucination category"
    gate_store.save(ctx)

    blockers = treatment_blockers(ctx)
    assert blockers
    assert blockers[0]["gap_type"] == "stale"
    assert _risk_treatment_blockers(ctx)


def test_open_high_safety_finding_requires_treatment(gate_store):
    ctx = _ctx()
    ctx.safety_findings.append(
        SafetyFinding(
            session_id=ctx.session_id,
            stage_id=3,
            risk_type="unsupported_claim",
            severity="high",
            location="stage_3",
            description="Unsupported claim in generated answer",
            recommended_action="Add evidence",
            requires_human_review=True,
        )
    )
    gate_store.save(ctx)

    assert treatment_blockers(ctx)
    assert _risk_treatment_blockers(ctx)


def test_public_demo_is_exempt(gate_store):
    ctx = _ctx(data_classification="public_demo")
    gate_store.save(ctx)

    assert treatment_blockers(ctx) == []
    assert _risk_treatment_blockers(ctx) == []


def test_resolution_operation_points_to_treatment_api(gate_store):
    ctx = _ctx()
    gate_store.save(ctx)

    operations = build_stage_resolution_operations(ctx, 4)
    operation = next(
        item for item in operations if item.required_resolution == "complete_risk_treatment"
    )

    assert operation.can_execute_via_api is True
    assert operation.api_method == "POST"
    assert operation.api_path == f"/sessions/{ctx.session_id}/risk-treatments"


def test_review_rejects_same_actor_and_stale_version():
    ctx = _ctx()
    treatment = upsert_risk_treatment(
        ctx,
        source_type="failure_mode",
        source_id="FM-001",
        owner="owner-a",
        mitigation_plan="plan",
        status="completed",
        actor_id="editor-a",
        actor_role="editor",
    )
    with pytest.raises(RiskTreatmentAuthorizationError, match="differ"):
        review_risk_treatment(
            ctx,
            treatment_id=treatment.treatment_id,
            decision="accept",
            note="self review",
            actor_id="editor-a",
            actor_role="editor",
        )

    ctx.stage_1_output.failure_modes[0].category = "changed"
    with pytest.raises(RiskTreatmentStaleError, match="changed"):
        review_risk_treatment(
            ctx,
            treatment_id=treatment.treatment_id,
            decision="accept",
            note="stale",
            actor_id="reviewer-b",
            actor_role="editor",
        )


def test_version_change_clears_review_even_when_resubmitted_verbatim():
    ctx = _ctx()
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
    assert treatment_blockers(ctx) == []

    ctx.stage_1_output.failure_modes[0].category = "changed category"
    upsert_risk_treatment(
        ctx,
        source_type="failure_mode",
        source_id="FM-001",
        owner="owner-a",
        mitigation_plan="Add citation validation",
        status="completed",
        actor_id="editor-a",
        actor_role="editor",
    )

    assert treatment.reviewed_by == ""
    assert treatment.reviewed_at is None
    blockers = treatment_blockers(ctx)
    assert blockers
    assert blockers[0]["gap_type"] == "unreviewed"

    review_risk_treatment(
        ctx,
        treatment_id=treatment.treatment_id,
        decision="accept",
        note="re-reviewed for the new version",
        actor_id="reviewer-b",
        actor_role="editor",
    )
    assert treatment_blockers(ctx) == []
