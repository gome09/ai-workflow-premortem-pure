from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import settings
from core.models import SessionState
from core.session_service import SessionService
from scenarios import read_scenario_input
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


def _resolve_pending_actions(service: SessionService, session_id: str) -> None:
    ctx = service.get_session(session_id)
    assert ctx is not None
    if ctx.current_state == SessionState.S3_REVIEW:
        coverage = service.redteam_coverage_summary(session_id)
        missing_coverage = bool(
            coverage.get("missing_safety_finding_ids") or coverage.get("missing_node_ids")
        )
        if missing_coverage:
            service.generate_redteam_cases(session_id, stage=3)
            cases = service.list_redteam_cases(session_id)
            for case in cases:
                if case.get("status") == "draft":
                    service.approve_redteam_case(
                        session_id, case.get("redteam_case_id"), note="test approve redteam"
                    )
            cases = service.list_redteam_cases(session_id)
            for case in cases:
                if case.get("status") == "approved":
                    service.redteam_case_to_eval_case(session_id, case.get("redteam_case_id"))
            refreshed = service.redteam_coverage_summary(session_id)
            if refreshed.get("synced_eval_ids_without_redteam_dataset"):
                service.create_redteam_dataset(session_id)
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
        decision = "approve"
        if action.action_type == "verify_evidence":
            decision = "verify_evidence"
        elif action.action_type == "edit":
            pytest.fail(f"Unexpected edit blocker in mock scenario flow: {action.action_id}")
        service.resolve_action_with_result(
            session_id=session_id,
            action_id=action.action_id,
            decision=decision,
            note="test auto resolve",
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


def test_create_session_attaches_builtin_scenario(monkeypatch, isolated_service):
    service = isolated_service
    monkeypatch.setattr(settings, "default_scenario_id", "")

    ctx = service.create_session(scenario_id="university_course_qa")
    assert ctx.selected_scenario_id == "university_course_qa"
    assert ctx.scenario_config["domain_profile"] == "university_ai"
    assert ctx.scenario_config["mock_fixture"] == "university_ai"


def test_builtin_scenario_input_enters_workflow(monkeypatch, isolated_service):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(settings, "storage_backend", "sqlite")
    monkeypatch.setattr(settings, "default_scenario_id", "")

    service = isolated_service
    ctx = service.create_session(scenario_id="generic_rag_demo")
    scenario_input = read_scenario_input("generic_rag_demo")
    ai_reply, updated = service.send_message(ctx.session_id, scenario_input)

    assert "信息收集完毕" in ai_reply
    assert updated.current_state == SessionState.S1_RUNNING
    assert updated.research_target
    assert updated.domain
    assert updated.goal


def test_mock_scenario_can_run_from_init_to_stage4(monkeypatch, isolated_service):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(settings, "storage_backend", "sqlite")
    monkeypatch.setattr(settings, "default_scenario_id", "")

    service = isolated_service
    ctx = service.create_session(scenario_id="generic_rag_demo")
    scenario_input = read_scenario_input("generic_rag_demo")

    service.send_message(ctx.session_id, scenario_input)
    max_turns = 12
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
    assert final_ctx.stage_1_output is not None
    assert final_ctx.stage_2_output is not None
    assert final_ctx.stage_3_output is not None
    assert final_ctx.stage_4_output is not None
    assert final_ctx.current_state == SessionState.COMPLETE
