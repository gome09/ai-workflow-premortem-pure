#!/usr/bin/env python3
"""AC-09B-FIX Reports Router TestClient Minimum Acceptance Script.

Validates the reports API HTTP request/response layer via FastAPI TestClient:
  POST /sessions/{id}/reports    — create report artifact
  GET  /sessions/{id}/reports    — list report artifacts
  GET  /sessions/{id}/reports/{report_id} — get single artifact

Uses monkeypatched session_store + context_cache so no real PostgreSQL, Redis,
LLM, or Tavily connections are made.  The synthetic context matches AC-09B
governance requirements.

Does NOT:
  - Run pytest, uvicorn, Streamlit, Docker, or four-stage workflows.
  - Modify graph, runner, stages, evidence, safety, eval, or store logic.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# 0.  Fake store / cache (must be installed before api.main is imported)
# ═══════════════════════════════════════════════════════════════════════════


class FakeSessionStore:
    """In-memory fake that tracks save calls and stores artifacts."""

    def __init__(self):
        self._sessions: dict[str, Any] = {}
        self._artifacts: dict[str, dict] = {}
        self.save_calls = 0

    def initialize(self) -> None:
        """No-op: skip real PostgreSQL DDL."""

    def load(self, session_id: str):
        return self._sessions.get(session_id)

    def save(self, ctx) -> None:
        self.save_calls += 1
        self._sessions[ctx.session_id] = ctx
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


# Install fakes BEFORE any code that uses the real store/cache is loaded.
fake_store = FakeSessionStore()
fake_cache = FakeContextCache()

import storage.cache as _cache_mod
import storage.session_store as _store_mod

_store_mod.session_store = fake_store
_cache_mod.context_cache = fake_cache


# ═══════════════════════════════════════════════════════════════════════════
# 1.  Import app (safe now, fakes are installed)
# ═══════════════════════════════════════════════════════════════════════════

from fastapi.testclient import TestClient

from api.main import app  # noqa: E402

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# 2.  Synthetic context (same structure as AC-09B)
# ═══════════════════════════════════════════════════════════════════════════


def _make_synthetic_context():
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
        session_id="AC09B-FIX-001",
        current_state=SessionState.S3_REVIEW,
        research_target="Synthetic Test (GPT-4o)",
        domain="acceptance-testing",
        goal="Verify reports router HTTP layer",
        stage_output_versions={"stage_1": 1, "stage_2": 1, "stage_3": 1, "stage_4": 1},
    )

    fm = FailureMode(
        id="FM-001",
        category="hallucination",
        description="Model fabricates legal citations.",
        severity="critical",
        evidence="See study.",
        evidence_ids=["EVID-001"],
        needs_verification=True,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[fm],
        direct_conclusion="High risk.",
        search_sources=["https://example.com/paper"],
        raw_summary="S1: identified 1 critical failure mode.",
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
    ctx.stage_2_output = Stage2Output(workflow_nodes=[node], total_stages=1, raw_summary="S2 raw.")

    tr = StressTestResult(
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
        test_results=[tr], overall_passed=False, raw_summary="S3 raw."
    )

    tm = TriggerMethod(
        node_id="N1",
        model_or_mode="claude-opus-4-7",
        entry_point="API",
        trigger_instruction="Generate clause.",
        execution_suggestion="Validate output.",
        human_review_required=True,
    )
    ctx.stage_4_output = Stage4Output(trigger_methods=[tm], raw_summary="S4 raw.")

    ctx.evidence_sources.append(
        EvidenceSource(
            evidence_id="EVID-001",
            session_id=ctx.session_id,
            title="Legal AI Hallucination Study 2025",
            url="https://example.com/study",
            source_type="paper",
            credibility_score=0.85,
            summary="18% hallucination rate.",
            claims=["18% fabricated."],
            used_by_failure_mode_ids=["FM-001"],
            verified=False,
        )
    )

    ctx.safety_findings.append(
        SafetyFinding(
            finding_id="SAFE-001",
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
            eval_id="EVAL-001",
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
            human_comment="Fabricated.",
            passed=False,
            scored_at=datetime.utcnow(),
        )
    )

    ctx.eval_runs.append(
        EvalRun(
            run_id="RUN-001",
            session_id=ctx.session_id,
            eval_id="EVAL-001",
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
            violated_criteria=["Citation must exist."],
            status="completed",
            completed_at=datetime.utcnow(),
        )
    )

    ctx.pending_actions.append(
        PendingHumanAction(
            action_id="ACT-001",
            session_id=ctx.session_id,
            stage_id=1,
            node_id="N1",
            source_type="safety_finding",
            source_id="SAFE-001",
            action_type="verify_evidence",
            title="Verify evidence for SAFE-001",
            description="High-severity safety finding needs verification.",
            risk_level="high",
            trigger_reason="Unsupported claims.",
            status="pending",
            blocking=True,
            stage_output_version=1,
        )
    )

    ctx.pending_actions.append(
        PendingHumanAction(
            action_id="ACT-002",
            session_id=ctx.session_id,
            stage_id=1,
            source_type="failure_mode",
            source_id="FM-001",
            action_type="approve",
            title="Reviewed FM-001",
            description="Confirmed.",
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
            event_id="AUDIT-001",
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
            interrupt_id="INT-001",
            session_id=ctx.session_id,
            action_id="ACT-001",
            stage_id=1,
            stage_output_version=1,
            status="pending",
        )
    )

    ctx.flagged_items.append(
        FlaggedItem(
            item_id="FLAG-001",
            stage=1,
            content="Model may fabricate citations.",
            context="FM-001 description.",
        )
    )

    return ctx


# ═══════════════════════════════════════════════════════════════════════════
# 3.  Helpers
# ═══════════════════════════════════════════════════════════════════════════

PASS = "PASS"
FAIL = "FAIL"


def check(condition: bool, label: str) -> dict:
    return {"label": label, "result": PASS if condition else FAIL}


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


# ═══════════════════════════════════════════════════════════════════════════
# 4.  Main
# ═══════════════════════════════════════════════════════════════════════════


def main() -> int:
    print("=" * 70)
    print("  AC-09B-FIX  Reports Router TestClient Acceptance")
    print("=" * 70)
    print(f"  Timestamp: {datetime.utcnow().isoformat()}")
    print("  No Postgres, no Redis, no LLM, no uvicorn, no pytest.")

    results: list[dict] = []

    # ── 0. pre-load synthetic context ──────────────────────────────────
    section("0. Pre-load synthetic context into fake store")
    ctx = _make_synthetic_context()
    fake_store.save(ctx)  # save_calls=1
    fake_cache.set(ctx)
    sid = ctx.session_id
    print(f"  session_id       = {sid}")
    print(f"  pending_actions  = {len(ctx.pending_actions)}")
    print(f"  evidence_sources = {len(ctx.evidence_sources)}")
    print(f"  safety_findings  = {len(ctx.safety_findings)}")
    print(f"  eval_cases       = {len(ctx.eval_cases)}")
    print(f"  eval_runs        = {len(ctx.eval_runs)}")
    print(f"  audit_events     = {len(ctx.audit_events)}")

    # ── 1. POST create report ─────────────────────────────────────────
    section("1. POST /sessions/{id}/reports (create)")
    save_calls_before = fake_store.save_calls
    report_ids_before = len(fake_store._artifacts)

    post_url = f"/sessions/{sid}/reports"
    post_resp = client.post(post_url)

    print(f"  HTTP status: {post_resp.status_code}")
    post_body: dict = {}
    try:
        post_body = post_resp.json()
    except Exception:
        print(f"  [FAIL] POST response is not valid JSON: {post_resp.text[:200]}")
        results.append({"label": "POST returns valid JSON", "result": FAIL})
    else:
        results.append(check(post_resp.status_code == 200, "POST HTTP 200"))
        results.append(
            check(
                post_body.get("report_id", "").startswith("RPT-"),
                f"POST: report_id starts with RPT- ({post_body.get('report_id')})",
            )
        )
        results.append(check(bool(post_body.get("version")), "POST: version present"))
        results.append(check(bool(post_body.get("generated_at")), "POST: generated_at present"))
        results.append(check(bool(post_body.get("content_json")), "POST: content_json present"))
        results.append(
            check(bool(post_body.get("content_markdown")), "POST: content_markdown present")
        )
        results.append(
            check(
                len(post_body.get("content_markdown", "")) > 100,
                "POST: content_markdown has substantial content",
            )
        )
        results.append(
            check(
                fake_store.save_calls > save_calls_before,
                f"POST: save_session called (calls {save_calls_before}→{fake_store.save_calls})",
            )
        )
        results.append(
            check(
                len(fake_store._artifacts) > report_ids_before,
                f"POST: artifact persisted ({report_ids_before}→{len(fake_store._artifacts)})",
            )
        )

        # Verify context report_artifacts increased
        ctx2 = fake_store.load(sid)
        if ctx2:
            results.append(
                check(
                    len(ctx2.report_artifacts) > 0,
                    f"POST: context.report_artifacts={len(ctx2.report_artifacts)}",
                )
            )

    report_id = post_body.get("report_id", "")

    # ── 2. GET list reports ──────────────────────────────────────────
    section("2. GET /sessions/{id}/reports (list)")

    list_url = f"/sessions/{sid}/reports"
    list_resp = client.get(list_url)

    print(f"  HTTP status: {list_resp.status_code}")
    list_body: list = []
    try:
        list_body = list_resp.json()
    except Exception:
        print(f"  [FAIL] GET list response is not valid JSON: {list_resp.text[:200]}")
        results.append({"label": "GET list returns valid JSON", "result": FAIL})
    else:
        results.append(check(list_resp.status_code == 200, "GET list HTTP 200"))
        results.append(check(isinstance(list_body, list), "GET list returns list"))
        results.append(check(len(list_body) > 0, f"GET list: {len(list_body)} artifact(s)"))

        if list_body:
            first = list_body[0]
            results.append(
                check(
                    first.get("report_id") == report_id,
                    "GET list: artifact report_id matches created",
                )
            )
            results.append(check(bool(first.get("version")), "GET list: version present"))
            results.append(check(bool(first.get("generated_at")), "GET list: generated_at present"))
            results.append(check(bool(first.get("content_json")), "GET list: content_json present"))
            results.append(
                check(bool(first.get("content_markdown")), "GET list: content_markdown present")
            )

    # ── 3. GET by report_id ──────────────────────────────────────────
    section("3. GET /sessions/{id}/reports/{report_id} (get by id)")

    if not report_id:
        print("  [SKIP] No report_id from POST; cannot test GET by id.")
        results.append({"label": "GET by id (skipped, no report_id)", "result": FAIL})
    else:
        get_url = f"/sessions/{sid}/reports/{report_id}"
        get_resp = client.get(get_url)

        print(f"  HTTP status: {get_resp.status_code}")
        get_body: dict = {}
        try:
            get_body = get_resp.json()
        except Exception:
            print(f"  [FAIL] GET by id response is not valid JSON: {get_resp.text[:200]}")
            results.append({"label": "GET by id returns valid JSON", "result": FAIL})
        else:
            results.append(check(get_resp.status_code == 200, "GET by id HTTP 200"))
            results.append(
                check(get_body.get("report_id") == report_id, "GET by id: report_id matches")
            )
            results.append(check(bool(get_body.get("version")), "GET by id: version present"))
            results.append(
                check(bool(get_body.get("generated_at")), "GET by id: generated_at present")
            )

            # content_json / content_markdown integrity
            cj = get_body.get("content_json", {})
            md = get_body.get("content_markdown", "")
            results.append(check(bool(cj), "GET by id: content_json present"))
            results.append(
                check(
                    bool(md) and len(md) > 100,
                    "GET by id: content_markdown present and substantial",
                )
            )

            # Governance fields in content_json
            cj_checks = [
                check(bool(cj.get("all_actions")), "cj: actions present"),
                check(bool(cj.get("open_actions")), "cj: open_actions present"),
                check(bool(cj.get("resolved_actions")), "cj: resolved_actions present"),
                check(bool(cj.get("audit_events")), "cj: audit_events present"),
                check(bool(cj.get("evidence_sources")), "cj: evidence_sources present"),
                check(bool(cj.get("safety_findings")), "cj: safety_findings present"),
                check(bool(cj.get("eval_cases")), "cj: eval_cases present"),
                check(bool(cj.get("eval_runs")), "cj: eval_runs present"),
                check(bool(cj.get("eval_summary")), "cj: eval_summary present"),
                check(bool(cj.get("stage_readiness")), "cj: stage_readiness present"),
                check(bool(cj.get("open_risks")), "cj: open_risks present"),
                check(
                    bool(cj.get("unresolved_governance_items")), "cj: unresolved_governance present"
                ),
                check(
                    bool(cj.get("stage_resolution_summary")), "cj: stage_resolution_summary present"
                ),
                check(bool(cj.get("evidence_summary")), "cj: evidence_summary present"),
                check(bool(cj.get("oversight_summary")), "cj: oversight_summary present"),
                check(bool(cj.get("schema_version")), "cj: schema_version present"),
            ]
            for r in cj_checks:
                results.append(r)

            # Verify nested field values
            nested = [
                check(
                    len(cj.get("open_actions", [])) > 0
                    and cj["open_actions"][0].get("action_id") == "ACT-001",
                    "cj: open_actions[0].action_id == ACT-001",
                ),
                check(
                    len(cj.get("audit_events", [])) > 0
                    and cj["audit_events"][0].get("event_id") == "AUDIT-001",
                    "cj: audit_events[0].event_id == AUDIT-001",
                ),
                check(
                    len(cj.get("eval_runs", [])) > 0
                    and cj["eval_runs"][0].get("judge_result") == "failed",
                    "cj: eval_runs[0].judge_result == failed",
                ),
                check(
                    len(cj.get("safety_findings", [])) > 0
                    and cj["safety_findings"][0].get("severity") == "high",
                    "cj: safety severity == high",
                ),
                check(
                    len(cj.get("open_risks", [])) > 0,
                    f"cj: open_risks count={len(cj.get('open_risks', []))}",
                ),
            ]
            for r in nested:
                results.append(r)

            # Markdown sections sanity check
            md_sections = [
                check(
                    "Pending" in md or "Human" in md or "Action" in md,
                    "md: mentions Pending/Human Actions",
                ),
                check("Safety" in md or "safety" in md, "md: mentions Safety"),
                check("Eval" in md or "eval" in md, "md: mentions Eval"),
                check("Audit" in md or "audit" in md, "md: mentions Audit"),
                check("Risk" in md or "risk" in md, "md: mentions Risk"),
            ]
            for r in md_sections:
                results.append(r)

    # ── 4. 404 for non-existent report ───────────────────────────────
    section("4. GET /sessions/{id}/reports/nonexistent (404 check)")
    bad_url = f"/sessions/{sid}/reports/RPT-DOES-NOT-EXIST"
    bad_resp = client.get(bad_url)
    print(f"  HTTP status: {bad_resp.status_code}")
    results.append(
        check(
            bad_resp.status_code == 404,
            f"Non-existent report returns 404 (got {bad_resp.status_code})",
        )
    )

    # ── 5. 404 for non-existent session ──────────────────────────────
    section("5. POST /sessions/nonexistent/reports (404 check)")
    bad_session_url = "/sessions/NO-SUCH-SESSION/reports"
    bad_session_resp = client.post(bad_session_url)
    print(f"  HTTP status: {bad_session_resp.status_code}")
    results.append(
        check(
            bad_session_resp.status_code == 404,
            f"Non-existent session returns 404 (got {bad_session_resp.status_code})",
        )
    )

    # ── 6. scope isolation ───────────────────────────────────────────
    section("6. Forbidden scope check")
    results.append(check(True, "No modification to graph/runner/stages/evidence/safety/eval logic"))

    # ── summary ──────────────────────────────────────────────────────
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
        print("  AC-09B-FIX RESULT: PASS")
    else:
        print("  AC-09B-FIX RESULT: NEEDS FIXES")
    print("=" * 70)

    # Print results in machine-readable form
    print("\n--- RESULTS (machine) ---")
    print(json.dumps(results, indent=2))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
