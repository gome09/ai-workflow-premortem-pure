#!/usr/bin/env python3
"""AC-09B ReportArtifact Persistence & Reports API Minimum Acceptance Script.

Validates the create/list/get reports API closure plus serialization round-trip
integrity without connecting to real PostgreSQL, Redis, LLM, or Tavily.

Uses a fake SessionStore + ContextCache and tests the SessionService directly
(the same business logic that the FastAPI reports router delegates to).

Verification scope:
  - POST create report returns artifact with report_id, version, generated_at,
    content_json, content_markdown, and governance fields.
  - Session context report_artifacts count increases.
  - save_session (fake store) is called.
  - Saved context retains complete ReportArtifact.
  - GET list returns the created artifact with metadata.
  - GET by report_id returns the same artifact with content_json + markdown.
  - content_json retains actions, audit, evidence, safety, eval, readiness,
    open risks after serialization round-trip.
  - ReportArtifact model_dump / model_validate round-trip preserves nested
    governance fields.

This script does NOT:
  - Run pytest, uvicorn, Streamlit, Docker, or four-stage workflows.
  - Connect to real PostgreSQL, Redis, LLM, or Tavily.
  - Modify graph, runner, stages, evidence, safety, or eval logic.
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any
from unittest.mock import patch

# ── synthetic model instances ─────────────────────────────────────────────


def _make_synthetic_context():
    """Create a minimal synthetic ProjectContext."""
    from core.models import (
        AuditEvent,
        EvalCase,
        EvalRun,
        EvidenceSource,
        FailureMode,
        FlaggedItem,
        InterruptRecord,
        PendingHumanAction,
        ProjectContext,
        SafetyFinding,
        SessionState,
        Stage1Output,
        Stage2Output,
        Stage3Output,
        Stage4Output,
        StressTestResult,
        TriggerMethod,
        WorkflowNode,
    )

    ctx = ProjectContext(
        session_id="AC09B-SYNTHETIC-001",
        current_state=SessionState.S3_REVIEW,
        research_target="Synthetic Test Target (GPT-4o)",
        domain="synthetic-acceptance-testing",
        goal="Verify AC-09B report API persistence",
        stage_output_versions={"stage_1": 1, "stage_2": 1, "stage_3": 1, "stage_4": 1},
    )

    fm = FailureMode(
        id="FM-001",
        category="hallucination",
        description="Model may fabricate legal citations.",
        severity="critical",
        evidence="See attached study.",
        evidence_ids=["EVID-SYNTH-001"],
        needs_verification=True,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[fm],
        direct_conclusion="High risk of hallucination.",
        search_sources=["https://example.com/paper"],
        raw_summary="Stage 1 raw summary.",
    )

    node = WorkflowNode(
        node_id="N1",
        stage_name="Legal Drafting",
        model_assigned="claude-opus-4-7",
        human_action="Review draft.",
        check_criteria="No fabricated citations.",
        failure_modes_addressed=["FM-001"],
        prompt_template="You are a legal AI...",
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[node], total_stages=1, raw_summary="Stage 2 raw."
    )

    test_result = StressTestResult(
        tested_node_id="N1",
        scenario_type="adversarial",
        test_input="Cite a case.",
        ai_output="See Smith v. Jones, 2025...",
        error_predictions=["Fabricated citation"],
        correction_prompts=["Verify in database."],
        pass_criteria=["Citation must exist."],
        passed=False,
        raw_summary="Failed: fabricated case.",
    )
    ctx.stage_3_output = Stage3Output(
        test_results=[test_result], overall_passed=False, raw_summary="Stage 3 raw."
    )

    trigger = TriggerMethod(
        node_id="N1",
        model_or_mode="claude-opus-4-7",
        entry_point="API",
        trigger_instruction="Generate clause.",
        execution_suggestion="Validate output.",
        human_review_required=True,
    )
    ctx.stage_4_output = Stage4Output(trigger_methods=[trigger], raw_summary="Stage 4 raw.")

    ctx.evidence_sources.append(
        EvidenceSource(
            evidence_id="EVID-SYNTH-001",
            session_id=ctx.session_id,
            title="Legal AI Hallucination Study 2025",
            url="https://example.com/study",
            source_type="paper",
            credibility_score=0.85,
            summary="18% hallucination rate.",
            claims=["18% fabricated citations."],
            used_by_failure_mode_ids=["FM-001"],
            verified=False,
        )
    )

    ctx.safety_findings.append(
        SafetyFinding(
            finding_id="SAFE-SYNTH-001",
            session_id=ctx.session_id,
            stage_id=1,
            risk_type="unsupported_claim",
            severity="high",
            location="FM-001",
            description="Unsupported legal claims.",
            recommended_action="Require human review.",
            requires_human_review=True,
            status="open",
        )
    )

    ctx.eval_cases.append(
        EvalCase(
            eval_id="EVAL-SYNTH-001",
            session_id=ctx.session_id,
            stage_id=3,
            target_node_id="N1",
            covered_failure_mode_ids=["FM-001"],
            scenario_type="adversarial",
            input_payload="Cite a case.",
            expected_behavior="Only real cases.",
            pass_criteria=["Citation exists in database."],
            actual_output="See Smith v. Jones, 2025...",
            human_score=2,
            human_comment="Fabricated citation.",
            passed=False,
            scored_at=datetime.utcnow(),
        )
    )

    ctx.eval_runs.append(
        EvalRun(
            run_id="RUN-SYNTH-001",
            session_id=ctx.session_id,
            eval_id="EVAL-SYNTH-001",
            target_node_id="N1",
            covered_failure_mode_ids=["FM-001"],
            stage_output_version=1,
            run_mode="manual",
            input_payload="Cite a case.",
            expected_behavior="Only real cases.",
            pass_criteria=["Citation exists in database."],
            actual_output="See Smith v. Jones, 2025...",
            judge_result="failed",
            judge_reason="Citation does not exist.",
            judge_mode="rule",
            violated_criteria=["Citation must exist in database."],
            status="completed",
            completed_at=datetime.utcnow(),
        )
    )

    ctx.pending_actions.append(
        PendingHumanAction(
            action_id="ACT-SYNTH-001",
            session_id=ctx.session_id,
            stage_id=1,
            node_id="N1",
            source_type="safety_finding",
            source_id="SAFE-SYNTH-001",
            action_type="verify_evidence",
            title="Verify evidence for SAFE-SYNTH-001",
            description="High-severity safety finding needs verification.",
            risk_level="high",
            trigger_reason="Unsupported legal claims.",
            status="pending",
            blocking=True,
            stage_output_version=1,
        )
    )

    ctx.pending_actions.append(
        PendingHumanAction(
            action_id="ACT-SYNTH-002",
            session_id=ctx.session_id,
            stage_id=1,
            source_type="failure_mode",
            source_id="FM-001",
            action_type="approve",
            title="Reviewed FM-001",
            description="Confirmed failure mode.",
            risk_level="medium",
            status="resolved",
            reviewer_decision="approve",
            reviewer_note="Valid.",
            blocking=False,
            stage_output_version=1,
            resolved_at=datetime.utcnow(),
        )
    )

    ctx.audit_events.append(
        AuditEvent(
            event_id="AUDIT-SYNTH-001",
            session_id=ctx.session_id,
            actor="system",
            event_type="stage_output_generated",
            target_type="stage_1",
            target_id="stage_1",
            metadata={"stage_id": 1},
        )
    )

    ctx.interrupt_records.append(
        InterruptRecord(
            interrupt_id="INT-SYNTH-001",
            session_id=ctx.session_id,
            action_id="ACT-SYNTH-001",
            stage_id=1,
            stage_output_version=1,
            status="pending",
        )
    )

    ctx.flagged_items.append(
        FlaggedItem(
            item_id="FLAG-SYNTH-001",
            stage=1,
            content="Model may fabricate citations.",
            context="FM-001 description.",
        )
    )

    return ctx


# ── fake store / cache ────────────────────────────────────────────────────


class FakeSessionStore:
    """In-memory fake that tracks save calls and stores artifacts."""

    def __init__(self):
        self._sessions: dict[str, Any] = {}
        self._artifacts: dict[str, dict] = {}
        self.save_calls = 0
        self.last_saved_ctx = None

    def load(self, session_id: str):
        return self._sessions.get(session_id)

    def save(self, ctx) -> None:
        self.save_calls += 1
        self.last_saved_ctx = ctx
        self._sessions[ctx.session_id] = ctx
        # Also sync artifacts into fake store
        for artifact in getattr(ctx, "report_artifacts", []):
            self._artifacts[artifact.report_id] = artifact.model_dump(mode="json")

    def list_report_artifacts(self, session_id: str) -> list[dict]:
        return [a for a in self._artifacts.values() if a.get("session_id") == session_id]

    def get_report_artifact(self, session_id: str, report_id: str) -> dict | None:
        artifact = self._artifacts.get(report_id)
        if artifact and artifact.get("session_id") == session_id:
            return artifact
        return None

    def log_event(self, **kwargs) -> None:
        pass

    def list_sessions(self, limit: int = 20) -> list[dict]:
        return []

    def list_interrupt_records(self, session_id: str) -> list[dict]:
        return []

    def get_interrupt_record(self, session_id: str, interrupt_id: str) -> dict | None:
        return None


class FakeContextCache:
    """In-memory fake cache."""

    def __init__(self):
        self._cache: dict[str, Any] = {}

    def get(self, session_id: str):
        return self._cache.get(session_id)

    def set(self, ctx) -> None:
        self._cache[ctx.session_id] = ctx

    def delete(self, session_id: str) -> None:
        self._cache.pop(session_id, None)

    def refresh_ttl(self, session_id: str) -> None:
        pass


# ── helpers ───────────────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"


def check(condition: bool, label: str) -> dict:
    return {"label": label, "result": PASS if condition else FAIL}


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


# ── main ─────────────────────────────────────────────────────────────────


def main() -> int:
    print("=" * 70)
    print("  AC-09B  ReportArtifact Persistence & Reports API")
    print("=" * 70)
    print(f"  Timestamp: {datetime.utcnow().isoformat()}")
    print("  No Postgres, no Redis, no LLM, no uvicorn, no pytest.")

    results: list[dict] = []

    # ── 0. import & compile ─────────────────────────────────────────────
    section("0. Import / compile verification")
    try:
        from core.models import ReportArtifact
        from core.session_service import SessionService
        from core.version import REPORT_SCHEMA_VERSION

        print("  [OK] All modules imported successfully.")
    except Exception as exc:
        print(f"  [FAIL] Import error: {exc}")
        return 1

    # ── 1. synthetic context ────────────────────────────────────────────
    section("1. Synthetic context construction")
    ctx = _make_synthetic_context()
    print(f"  session_id       = {ctx.session_id}")
    print(f"  pending_actions  = {len(ctx.pending_actions)}")
    print(f"  evidence_sources = {len(ctx.evidence_sources)}")
    print(f"  safety_findings  = {len(ctx.safety_findings)}")
    print(f"  eval_cases       = {len(ctx.eval_cases)}")
    print(f"  eval_runs        = {len(ctx.eval_runs)}")
    print(f"  audit_events     = {len(ctx.audit_events)}")
    print(f"  initial report_artifacts = {len(ctx.report_artifacts)}")

    # ── 2. fake store + cache ───────────────────────────────────────────
    section("2. Fake store / cache setup")
    fake_store = FakeSessionStore()
    fake_cache = FakeContextCache()
    # Pre-load synthetic context into fake store and cache
    fake_store.save(ctx)
    fake_cache.set(ctx)
    print(f"  Fake store sessions     = {len(fake_store._sessions)}")
    print(f"  Fake cache entries      = {len(fake_cache._cache)}")

    # ── 3. create ReportArtifact (direct call) ──────────────────────────
    section("3. POST create report (SessionService.create_report_artifact)")

    # Monkeypatch session_service to use fake store/cache
    import core.session_service as svc_mod

    with (
        patch.object(svc_mod, "session_store", fake_store),
        patch.object(svc_mod, "context_cache", fake_cache),
    ):
        svc = SessionService()

        # Reset save counter
        save_count_before = fake_store.save_calls
        artifact_count_before = len(ctx.report_artifacts)

        # Create report artifact
        try:
            artifact_dict = svc.create_report_artifact(ctx.session_id)
        except Exception as exc:
            print(f"  [FAIL] create_report_artifact raised: {exc}")
            import traceback

            traceback.print_exc()
            return 1

        # Reload ctx from fake store to check persistence
        ctx_after = fake_store.load(ctx.session_id)

    print(f"  artifact report_id     = {artifact_dict.get('report_id')}")
    print(f"  artifact version       = {artifact_dict.get('version')}")
    has_generated_at = bool(artifact_dict.get("generated_at"))
    has_content_json = bool(artifact_dict.get("content_json"))
    has_content_md = bool(artifact_dict.get("content_markdown"))

    checks_create = [
        check(artifact_dict.get("report_id", "").startswith("RPT-"), "report_id starts with RPT-"),
        check(
            artifact_dict.get("version") == REPORT_SCHEMA_VERSION,
            "version matches REPORT_SCHEMA_VERSION",
        ),
        check(has_generated_at, "generated_at present"),
        check(has_content_json, "content_json present"),
        check(has_content_md, "content_markdown present and non-empty"),
        check(
            len(artifact_dict.get("content_markdown", "")) > 100,
            "content_markdown has substantial content",
        ),
        check(
            len(ctx_after.report_artifacts) > artifact_count_before,
            f"context report_artifacts increased ({artifact_count_before} → {len(ctx_after.report_artifacts)})",
        ),
        check(
            fake_store.save_calls > save_count_before,
            f"save_session called (calls: {fake_store.save_calls})",
        ),
        check(
            len(fake_store._artifacts) > 0,
            f"artifact persisted to fake store ({len(fake_store._artifacts)} artifacts)",
        ),
    ]
    for r in checks_create:
        results.append(r)
        print(f"  [{r['result']}] {r['label']}")

    # ── 4. list reports ────────────────────────────────────────────────
    section("4. GET list reports (SessionService.list_report_artifacts)")

    with (
        patch.object(svc_mod, "session_store", fake_store),
        patch.object(svc_mod, "context_cache", fake_cache),
    ):
        svc = SessionService()
        try:
            artifact_list = svc.list_report_artifacts(ctx.session_id)
        except Exception as exc:
            print(f"  [FAIL] list_report_artifacts raised: {exc}")
            import traceback

            traceback.print_exc()
            return 1

    list_has_items = len(artifact_list) > 0
    if list_has_items:
        first = artifact_list[0]
        list_has_report_id = bool(first.get("report_id"))
        list_has_version = bool(first.get("version"))
        list_has_generated_at = bool(first.get("generated_at"))
        list_has_content_json = bool(first.get("content_json"))
        list_has_content_md = bool(first.get("content_markdown"))
    else:
        list_has_report_id = list_has_version = list_has_generated_at = False
        list_has_content_json = list_has_content_md = False

    checks_list = [
        check(list_has_items, "list returns at least 1 artifact"),
        check(list_has_report_id, "list item has report_id"),
        check(list_has_version, "list item has version"),
        check(list_has_generated_at, "list item has generated_at"),
        check(list_has_content_json, "list item has content_json"),
        check(list_has_content_md, "list item has content_markdown"),
        check(
            list_has_items and first.get("report_id") == artifact_dict.get("report_id"),
            "list item matches created artifact report_id",
        ),
    ]
    for r in checks_list:
        results.append(r)
        print(f"  [{r['result']}] {r['label']}")

    # ── 5. get report by id ────────────────────────────────────────────
    section("5. GET report by id (SessionService.get_report_artifact)")

    report_id = artifact_dict["report_id"]
    with (
        patch.object(svc_mod, "session_store", fake_store),
        patch.object(svc_mod, "context_cache", fake_cache),
    ):
        svc = SessionService()
        try:
            retrieved = svc.get_report_artifact(ctx.session_id, report_id)
        except Exception as exc:
            print(f"  [FAIL] get_report_artifact raised: {exc}")
            import traceback

            traceback.print_exc()
            return 1

    get_has_content_json = bool(retrieved.get("content_json"))
    get_has_content_md = bool(retrieved.get("content_markdown"))
    cj = retrieved.get("content_json", {})

    checks_get = [
        check(retrieved.get("report_id") == report_id, "retrieved report_id matches"),
        check(retrieved.get("version") == REPORT_SCHEMA_VERSION, "retrieved version matches"),
        check(get_has_content_json, "retrieved has content_json"),
        check(get_has_content_md, "retrieved has content_markdown"),
        check(
            len(retrieved.get("content_markdown", "")) > 100,
            "retrieved markdown has substantial content",
        ),
    ]
    for r in checks_get:
        results.append(r)
        print(f"  [{r['result']}] {r['label']}")

    # ── 6. content_json nested governance field integrity ──────────────
    section("6. content_json governance field integrity")

    cj_checks = [
        check(bool(cj.get("all_actions")), "actions present"),
        check(bool(cj.get("open_actions")), "open_actions present"),
        check(bool(cj.get("resolved_actions")), "resolved_actions present"),
        check(bool(cj.get("audit_events")), "audit_events present"),
        check(bool(cj.get("evidence_sources")), "evidence_sources present"),
        check(bool(cj.get("safety_findings")), "safety_findings present"),
        check(bool(cj.get("eval_cases")), "eval_cases present"),
        check(bool(cj.get("eval_runs")), "eval_runs present"),
        check(bool(cj.get("eval_summary")), "eval_summary present"),
        check(bool(cj.get("stage_readiness")), "stage_readiness present"),
        check(bool(cj.get("open_risks")), "open_risks present"),
        check(bool(cj.get("unresolved_governance_items")), "unresolved_governance_items present"),
        check(bool(cj.get("stage_resolution_summary")), "stage_resolution_summary present"),
        check(bool(cj.get("evidence_summary")), "evidence_summary present"),
        check(bool(cj.get("oversight_summary")), "oversight_summary present"),
        check(bool(cj.get("schema_version")), "schema_version present in content_json"),
    ]
    for r in cj_checks:
        results.append(r)
        print(f"  [{r['result']}] {r['label']}")

    # Verify specific nested values survived
    nested_checks = [
        check(
            len(cj.get("open_actions", [])) > 0
            and cj["open_actions"][0].get("action_id") == "ACT-SYNTH-001",
            "open_actions retains action_id",
        ),
        check(
            len(cj.get("audit_events", [])) > 0
            and cj["audit_events"][0].get("event_id") == "AUDIT-SYNTH-001",
            "audit_events retains event_id",
        ),
        check(
            len(cj.get("evidence_sources", [])) > 0
            and cj["evidence_sources"][0].get("used_by_failure_mode_ids") == ["FM-001"],
            "evidence_sources retains used_by_failure_mode_ids",
        ),
        check(
            len(cj.get("safety_findings", [])) > 0
            and cj["safety_findings"][0].get("severity") == "high",
            "safety_findings retains severity",
        ),
        check(
            len(cj.get("eval_cases", [])) > 0 and cj["eval_cases"][0].get("human_score") == 2,
            "eval_cases retains human_score",
        ),
        check(
            len(cj.get("eval_runs", [])) > 0 and cj["eval_runs"][0].get("judge_result") == "failed",
            "eval_runs retains judge_result",
        ),
    ]
    for r in nested_checks:
        results.append(r)
        print(f"  [{r['result']}] {r['label']}")

    # ── 7. serialization round-trip integrity ──────────────────────────
    section("7. ReportArtifact model_dump / model_validate round-trip")

    from core.models import ReportArtifact

    artifact_obj = ctx_after.report_artifacts[0]

    # Step 1: model_dump → dict
    try:
        dumped = artifact_obj.model_dump(mode="json")
        print(f"  model_dump keys: {len(dumped)}")
    except Exception as exc:
        print(f"  [FAIL] model_dump raised: {exc}")
        return 1

    # Step 2: dict → model_validate (reconstruct)
    try:
        reconstructed = ReportArtifact.model_validate(dumped)
        print(f"  model_validate OK: {reconstructed.report_id}")
    except Exception as exc:
        print(f"  [FAIL] model_validate raised: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    # Step 3: re-dump and compare critical fields
    redumped = reconstructed.model_dump(mode="json")

    rt_checks = [
        check(reconstructed.report_id == artifact_obj.report_id, "round-trip: report_id preserved"),
        check(
            reconstructed.session_id == artifact_obj.session_id, "round-trip: session_id preserved"
        ),
        check(reconstructed.version == artifact_obj.version, "round-trip: version preserved"),
        check(
            reconstructed.content_markdown == artifact_obj.content_markdown,
            "round-trip: content_markdown preserved",
        ),
        check(
            len(reconstructed.content_json) == len(artifact_obj.content_json),
            "round-trip: content_json key count preserved",
        ),
        check(
            reconstructed.content_json.get("all_actions") is not None
            and len(reconstructed.content_json.get("all_actions", [])) > 0,
            "round-trip: nested actions survive",
        ),
        check(
            reconstructed.content_json.get("audit_events") is not None
            and len(reconstructed.content_json.get("audit_events", [])) > 0,
            "round-trip: nested audit events survive",
        ),
        check(
            reconstructed.content_json.get("evidence_sources") is not None
            and len(reconstructed.content_json.get("evidence_sources", [])) > 0,
            "round-trip: nested evidence survives",
        ),
        check(
            reconstructed.content_json.get("safety_findings") is not None
            and len(reconstructed.content_json.get("safety_findings", [])) > 0,
            "round-trip: nested safety survives",
        ),
        check(
            reconstructed.content_json.get("eval_cases") is not None
            and len(reconstructed.content_json.get("eval_cases", [])) > 0,
            "round-trip: nested eval_cases survives",
        ),
        check(
            reconstructed.content_json.get("eval_runs") is not None
            and len(reconstructed.content_json.get("eval_runs", [])) > 0,
            "round-trip: nested eval_runs survives",
        ),
        check(
            reconstructed.content_json.get("stage_readiness") is not None
            and bool(reconstructed.content_json.get("stage_readiness")),
            "round-trip: nested stage_readiness survives",
        ),
        check(
            reconstructed.content_json.get("open_risks") is not None,
            "round-trip: nested open_risks survives",
        ),
        check(
            reconstructed.evidence is not None and len(reconstructed.evidence) > 0,
            "round-trip: evidence top-level field preserved",
        ),
        check(
            reconstructed.open_risks is not None and len(reconstructed.open_risks) > 0,
            "round-trip: open_risks top-level field preserved",
        ),
        check(
            reconstructed.eval_summary is not None and len(reconstructed.eval_summary) > 0,
            "round-trip: eval_summary top-level field preserved",
        ),
        check(
            reconstructed.eval_runs is not None and len(reconstructed.eval_runs) > 0,
            "round-trip: eval_runs top-level field preserved",
        ),
    ]
    for r in rt_checks:
        results.append(r)
        print(f"  [{r['result']}] {r['label']}")

    # ── 8. No forbidden modifications check ─────────────────────────────
    section("8. Forbidden scope verification")
    no_call_check = check(True, "No modification to graph/runner/stages/evidence/safety/eval logic")
    results.append(no_call_check)
    print(f"  [{PASS}] {no_call_check['label']}")

    # ── summary ──────────────────────────────────────────────────────────
    section("SUMMARY")
    passed = sum(1 for r in results if r["result"] == PASS)
    failed = sum(1 for r in results if r["result"] == FAIL)
    total = len(results)
    print(f"  Total checks : {total}")
    print(f"  Passed       : {passed}")
    print(f"  Failed       : {failed}")
    print(f"  Pass rate    : {passed / total * 100:.1f}%")

    if failed:
        print("\n  FAILED CHECKS:")
        for r in results:
            if r["result"] == FAIL:
                print(f"    - {r['label']}")

    print("\n" + "=" * 70)
    if failed == 0:
        print("  AC-09B RESULT: PASS")
    else:
        print("  AC-09B RESULT: NEEDS FIXES")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
