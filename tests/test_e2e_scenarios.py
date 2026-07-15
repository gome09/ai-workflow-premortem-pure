# tests/test_e2e_scenarios.py
"""WS-7: End-to-end workflow for all built-in scenarios.

Drives each scenario (generic_rag_demo, university_mental_health) from
INIT → COMPLETE in mock mode, asserting all four stage outputs are produced
and a deployment decision is attached to Stage 4.

Non-safety-bottom-line rules that require complex eval infrastructure
(eval_regression, redteam_coverage, trace_backfill_gap, stage3_eval_failure)
are disabled to keep the e2e test focused on cross-stage integrity and
deployment decision. Safety-bottom-line rules (expert_review,
cross_stage_integrity, missing_output, etc.) remain active.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import settings
from core.models import SessionState
from core.session_service import SessionService
from scenarios import read_scenario_input
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

SCENARIOS = [
    "generic_rag_demo",
    "university_mental_health",
]

# 非安全底线规则，在 e2e 测试中禁用以避免复杂的评测基础设施搭建。
# 安全底线规则（expert_review, cross_stage_integrity, missing_output 等）保持启用。
_DISABLED_RULES = "eval_regression,redteam_coverage,trace_backfill_gap,stage3_eval_failure"


def _resolve_pending_actions(service: SessionService, session_id: str) -> None:
    """Resolve all pending actions for the current stage.

    Handles evidence verification, safety finding resolution, and action
    resolution including escalate (expert_review) and edit actions.
    """
    ctx = service.get_session(session_id)
    assert ctx is not None
    if ctx.current_state in {SessionState.S1_REVIEW, SessionState.S1_RUNNING}:
        for evidence in ctx.evidence_sources:
            if not evidence.verified:
                service.verify_evidence(session_id, evidence.evidence_id, note="test verify")
        ctx = service.get_session(session_id)
        assert ctx is not None
    for finding in list(ctx.safety_findings):
        if finding.status == "open" and finding.requires_human_review:
            service.resolve_safety_finding(
                session_id,
                finding.finding_id,
                status="resolved",
                note="test resolve safety",
            )
    ctx = service.get_session(session_id)
    assert ctx is not None
    for action in list(ctx.get_pending_actions()):
        if action.status != "pending":
            continue
        decision = "approve"
        if action.action_type == "verify_evidence":
            decision = "verify_evidence"
        elif action.action_type == "escalate":
            # expert_review creates escalate actions for CRITICAL risk
            decision = "approve"
        elif action.action_type == "edit":
            # eval_coverage edit actions: resolve with "edit" + minimal payload
            decision = "edit"
        service.resolve_action_with_result(
            session_id=session_id,
            action_id=action.action_id,
            decision=decision,
            note="test auto resolve",
            payload_after={"note": "e2e auto resolve"} if decision == "edit" else None,
        )


@pytest.fixture
def isolated_service(tmp_path):
    db_path = tmp_path / "workflow.db"
    store = SQLiteSessionStore(str(db_path))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService()


def _run_scenario_to_completion(
    service: SessionService,
    scenario_id: str,
    max_turns: int = 20,
) -> None:
    ctx = service.create_session(scenario_id=scenario_id)
    scenario_input = read_scenario_input(scenario_id)

    service.send_message(ctx.session_id, scenario_input)
    for _ in range(max_turns):
        current = service.get_session(ctx.session_id)
        assert current is not None
        if current.current_state == SessionState.COMPLETE and current.stage_4_output is not None:
            break
        if current.current_state in {
            SessionState.S1_RUNNING,
            SessionState.S2_RUNNING,
            SessionState.S3_RUNNING,
            SessionState.S4_RUNNING,
        }:
            service.send_message(ctx.session_id, "开始")
            _resolve_pending_actions(service, ctx.session_id)
            continue
        if current.current_state in {
            SessionState.S1_REVIEW,
            SessionState.S2_REVIEW,
            SessionState.S3_REVIEW,
            SessionState.S4_REVIEW,
        }:
            _resolve_pending_actions(service, ctx.session_id)
            service.send_message(ctx.session_id, "确认")
            continue
        pytest.fail(f"Unexpected state in scenario workflow test: {current.current_state}")

    final_ctx = service.get_session(ctx.session_id)
    assert final_ctx is not None
    assert final_ctx.stage_1_output is not None, f"{scenario_id}: stage_1_output missing"
    assert final_ctx.stage_2_output is not None, f"{scenario_id}: stage_2_output missing"
    assert final_ctx.stage_3_output is not None, f"{scenario_id}: stage_3_output missing"
    assert final_ctx.stage_4_output is not None, f"{scenario_id}: stage_4_output missing"
    assert final_ctx.current_state == SessionState.COMPLETE, (
        f"{scenario_id}: expected COMPLETE, got {final_ctx.current_state}"
    )
    assert final_ctx.stage_4_output.deployment_decision is not None, (
        f"{scenario_id}: deployment_decision missing"
    )


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_e2e_scenario_completes_with_deployment_decision(
    monkeypatch, isolated_service, scenario_id
):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(settings, "storage_backend", "sqlite")
    monkeypatch.setattr(settings, "default_scenario_id", "")
    monkeypatch.setattr(settings, "gate_rules_disabled", _DISABLED_RULES)

    _run_scenario_to_completion(isolated_service, scenario_id, max_turns=20)
