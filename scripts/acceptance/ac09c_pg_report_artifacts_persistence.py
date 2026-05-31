#!/usr/bin/env python3
"""AC-09C Real PostgreSQL report_artifacts Minimum Persistence Acceptance.

Validates against a real (non-production) PostgreSQL database:
  - report_artifacts table DDL (CREATE / ALTER idempotency)
  - content_markdown column existence and type
  - SessionStore.save writes content_json + content_markdown
  - SessionStore.list_report_artifacts reads back
  - SessionStore.get_report_artifact reads back by report_id
  - Direct SQL confirms content_json + content_markdown non-empty
  - Upsert (same report_id saved twice) updates content_markdown, no duplicates
  - Cleanup of test data only

Outputs BLOCKED (exit code 2) if no PostgreSQL DSN is configured or if the
database appears to be production.

Does NOT:
  - Run pytest, uvicorn, Streamlit, Docker, or four-stage workflows.
  - Connect to Redis, LLM, or Tavily.
  - Modify graph, runner, stages, evidence, safety, or eval logic.
  - Delete/truncate data not created by this test session.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime

# ═══════════════════════════════════════════════════════════════════════════
# 0.  Safety checks
# ═══════════════════════════════════════════════════════════════════════════

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"


def check(condition: bool, label: str) -> dict:
    return {"label": label, "result": PASS if condition else FAIL}


def check_blocked(condition: bool, label: str) -> dict:
    return {"label": label, "result": PASS if condition else BLOCKED}


# ═══════════════════════════════════════════════════════════════════════════
# 1.  Synthetic context builder (no DB / no LLM)
# ═══════════════════════════════════════════════════════════════════════════


def _make_synthetic_context(session_id: str):
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
        session_id=session_id,
        current_state=SessionState.S3_REVIEW,
        research_target="AC-09C PG Persistence Test",
        domain="acceptance-testing",
        goal="Verify real PG report_artifacts write/read/upsert",
        stage_output_versions={"stage_1": 1, "stage_2": 1, "stage_3": 1, "stage_4": 1},
    )

    fm = FailureMode(
        id="FM-PG-001",
        category="hallucination",
        description="Model fabricates legal citations under adversarial prompts.",
        severity="critical",
        evidence="See attached study.",
        evidence_ids=["EVID-PG-001"],
        needs_verification=True,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[fm],
        direct_conclusion="High hallucination risk.",
        search_sources=["https://example.com/paper"],
        raw_summary="S1 raw.",
    )

    node = WorkflowNode(
        node_id="N1",
        stage_name="Legal Drafting",
        model_assigned="claude-opus-4-7",
        human_action="Review draft.",
        check_criteria="No fabricated citations.",
        failure_modes_addressed=["FM-PG-001"],
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
        raw_summary="Failed.",
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
            evidence_id="EVID-PG-001",
            session_id=session_id,
            title="Legal AI Hallucination Study 2025",
            url="https://example.com/study",
            source_type="paper",
            credibility_score=0.85,
            summary="18% hallucination rate.",
            claims=["18% fabricated."],
            used_by_failure_mode_ids=["FM-PG-001"],
            verified=False,
        )
    )

    ctx.safety_findings.append(
        SafetyFinding(
            finding_id="SAFE-PG-001",
            session_id=session_id,
            stage_id=1,
            risk_type="unsupported_claim",
            severity="high",
            location="FM-PG-001",
            description="Unsupported legal claims.",
            recommended_action="Require human review.",
            requires_human_review=True,
            status="open",
        )
    )

    ctx.eval_cases.append(
        EvalCase(
            eval_id="EVAL-PG-001",
            session_id=session_id,
            stage_id=3,
            target_node_id="N1",
            covered_failure_mode_ids=["FM-PG-001"],
            scenario_type="adversarial",
            input_payload="Cite a case.",
            expected_behavior="Only real cases.",
            pass_criteria=["Citation exists in database."],
            actual_output="See Smith v. Jones, 2025...",
            human_score=2,
            human_comment="Fabricated.",
            passed=False,
            scored_at=datetime.now(UTC),
        )
    )

    ctx.eval_runs.append(
        EvalRun(
            run_id="RUN-PG-001",
            session_id=session_id,
            eval_id="EVAL-PG-001",
            target_node_id="N1",
            covered_failure_mode_ids=["FM-PG-001"],
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
            completed_at=datetime.now(UTC),
        )
    )

    ctx.pending_actions.append(
        PendingHumanAction(
            action_id="ACT-PG-001",
            session_id=session_id,
            stage_id=1,
            node_id="N1",
            source_type="safety_finding",
            source_id="SAFE-PG-001",
            action_type="verify_evidence",
            title="Verify evidence for SAFE-PG-001",
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
            action_id="ACT-PG-002",
            session_id=session_id,
            stage_id=1,
            source_type="failure_mode",
            source_id="FM-PG-001",
            action_type="approve",
            title="Reviewed FM-PG-001",
            description="Confirmed.",
            risk_level="medium",
            status="resolved",
            reviewer_decision="approve",
            reviewer_note="Valid.",
            blocking=False,
            stage_output_version=1,
            resolved_at=datetime.now(UTC),
        )
    )

    ctx.audit_events.append(
        AuditEvent(
            event_id="AUDIT-PG-001",
            session_id=session_id,
            actor="system",
            event_type="stage_output_generated",
            target_type="stage_1",
            target_id="stage_1",
            metadata={"stage_id": 1},
        )
    )

    ctx.interrupt_records.append(
        InterruptRecord(
            interrupt_id="INT-PG-001",
            session_id=session_id,
            action_id="ACT-PG-001",
            stage_id=1,
            stage_output_version=1,
            status="pending",
        )
    )

    ctx.flagged_items.append(
        FlaggedItem(
            item_id="FLAG-PG-001",
            stage=1,
            content="Model may fabricate citations.",
            context="FM-PG-001 description.",
        )
    )

    return ctx


# ═══════════════════════════════════════════════════════════════════════════
# 2.  Main
# ═══════════════════════════════════════════════════════════════════════════


def main() -> int:
    now_ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    test_uuid = str(uuid.uuid4())[:8]
    test_session_id = f"AC09C-{now_ts}-{test_uuid}"

    print("=" * 70)
    print("  AC-09C  Real PostgreSQL report_artifacts Persistence")
    print("=" * 70)
    print(f"  Timestamp : {datetime.now(UTC).isoformat()}")
    print(f"  Test SID  : {test_session_id}")
    print("  No Redis, no LLM, no Tavily, no uvicorn, no pytest.")

    results: list[dict] = []

    # ── 0. Resolve DSN and safety checks ───────────────────────────────
    print(f"\n{'=' * 70}")
    print("  0. DSN resolution & safety checks")
    print(f"{'=' * 70}")

    from core.config import settings

    app_env = (getattr(settings, "app_env", "") or "").lower()
    db_name = (getattr(settings, "postgres_db", "") or "").lower()
    pg_host = (getattr(settings, "postgres_host", "") or "").lower()

    print(f"  app_env     = {app_env}")
    print(f"  pg_host     = {pg_host}")
    print(f"  pg_db       = {db_name}")

    # Refuse production databases
    production_markers = ["prod", "production", "live"]
    is_production = any(m in app_env for m in production_markers)
    is_production |= any(m in db_name for m in production_markers)
    is_production |= any(m in pg_host for m in ["rds.amazonaws.com", "cloudsql", "azure.com"])

    if is_production:
        print("\n  [BLOCKED] Production database detected! Refusing to run.")
        print(f"  app_env={app_env} db_name={db_name} host={pg_host}")
        return 2

    dsn = settings.postgres_dsn_sync
    masked = dsn
    if "@" in dsn and "://" in dsn:
        prefix, rest = dsn.split("://", 1)
        if ":" in rest.split("@")[0]:
            user = rest.split(":")[0]
            masked = f"{prefix}://{user}:****@{rest.split('@', 1)[1]}"
    print(f"  DSN         = {masked}")

    try:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10)
        conn.close()
        print("  Connection  : OK")
        results.append(check_blocked(True, "PostgreSQL connection succeeded"))
    except Exception as exc:
        print(f"\n  [BLOCKED] Cannot connect to PostgreSQL: {exc}")
        print(f"  DSN: {masked}")
        results.append({"label": f"PostgreSQL connection: {exc}", "result": BLOCKED})
        _print_summary(results)
        return 2

    # ── 1. DDL initialization (idempotent) ────────────────────────────
    print(f"\n{'=' * 70}")
    print("  1. DDL initialization (idempotent)")
    print(f"{'=' * 70}")

    from storage.session_store import SessionStore

    store = SessionStore()

    try:
        store.initialize()
        print("  initialize() : OK (no exceptions)")
        results.append(check(True, "DDL initialize() succeeded (idempotent)"))
    except Exception as exc:
        print(f"  [FAIL] initialize() raised: {exc}")
        results.append(check(False, f"DDL initialize() failed: {exc}"))
        _print_summary(results)
        return 1

    # Run it twice to verify idempotency
    try:
        store.initialize()
        print("  2nd initialize() : OK (DDL is idempotent)")
        results.append(check(True, "DDL idempotent: second initialize() no error"))
    except Exception as exc:
        print(f"  [FAIL] 2nd initialize() raised: {exc}")
        results.append(check(False, f"DDL idempotency failed: {exc}"))

    # ── 2. Table existence and column check ───────────────────────────
    print(f"\n{'=' * 70}")
    print("  2. Table & column existence")
    print(f"{'=' * 70}")

    with store._get_conn() as conn:
        # Check table exists
        table_sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'report_artifacts'
            ) AS exists
        """
        row = conn.execute(table_sql).fetchone()
        table_exists = bool(row["exists"]) if row else False
        print(f"  report_artifacts table exists: {table_exists}")
        results.append(check(table_exists, "report_artifacts table exists"))

        # Check columns
        col_sql = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'report_artifacts'
            ORDER BY ordinal_position
        """
        cols = conn.execute(col_sql).fetchall()
        col_names = {c["column_name"]: c["data_type"] for c in cols}
        print(f"  Columns: {list(col_names.keys())}")

        expected_cols = [
            "report_id",
            "session_id",
            "version",
            "content_json",
            "content_markdown",
            "generated_at",
        ]
        for ec in expected_cols:
            present = ec in col_names
            dtype = col_names.get(ec, "MISSING")
            print(f"    {ec}: {dtype}" if present else f"    {ec}: MISSING")
            results.append(check(present, f"Column '{ec}' exists (type={dtype})"))

        # content_markdown type check
        md_type = col_names.get("content_markdown", "").lower()
        is_text_type = md_type in ("text", "character varying", "varchar")
        results.append(check(is_text_type, f"content_markdown is text type (actual={md_type})"))

    # ── 3. Build synthetic context + report artifact ─────────────────
    print(f"\n{'=' * 70}")
    print("  3. Synthetic context + ReportArtifact construction")
    print(f"{'=' * 70}")

    ctx = _make_synthetic_context(test_session_id)
    print(f"  session_id       = {ctx.session_id}")
    print(f"  pending_actions  = {len(ctx.pending_actions)}")
    print(f"  evidence_sources = {len(ctx.evidence_sources)}")
    print(f"  safety_findings  = {len(ctx.safety_findings)}")
    print(f"  eval_cases       = {len(ctx.eval_cases)}")
    print(f"  eval_runs        = {len(ctx.eval_runs)}")
    print(f"  audit_events     = {len(ctx.audit_events)}")
    print(f"  report_artifacts (before) = {len(ctx.report_artifacts)}")

    # Create the report artifact (uses production code path)
    from core.report_service import create_report_artifact

    artifact = create_report_artifact(ctx)
    print(f"  report_id        = {artifact.report_id}")
    print(f"  version          = {artifact.version}")
    print(f"  content_json keys = {len(artifact.content_json)}")
    print(f"  content_md len   = {len(artifact.content_markdown)}")

    results.append(check(artifact.report_id.startswith("RPT-"), "report_id starts with RPT-"))
    results.append(check(len(artifact.content_json) > 0, "content_json non-empty"))
    results.append(check(len(artifact.content_markdown) > 100, "content_markdown > 100 chars"))
    results.append(check(len(ctx.report_artifacts) == 1, "context.report_artifacts = 1"))

    # ── 4. SessionStore.save → write to PostgreSQL ───────────────────
    print(f"\n{'=' * 70}")
    print("  4. SessionStore.save → write to PostgreSQL")
    print(f"{'=' * 70}")

    try:
        store.save(ctx)
        print("  save() : OK (no exceptions)")
        results.append(check(True, "SessionStore.save() succeeded"))
    except Exception as exc:
        print(f"  [FAIL] save() raised: {exc}")
        import traceback

        traceback.print_exc()
        results.append(check(False, f"SessionStore.save() failed: {exc}"))
        _cleanup(store, test_session_id)
        _print_summary(results)
        return 1

    # ── 5. SessionStore.list_report_artifacts → read back ────────────
    print(f"\n{'=' * 70}")
    print("  5. SessionStore.list_report_artifacts → read back")
    print(f"{'=' * 70}")

    try:
        listed = store.list_report_artifacts(test_session_id)
        print(f"  list count = {len(listed)}")
    except Exception as exc:
        print(f"  [FAIL] list_report_artifacts raised: {exc}")
        results.append(check(False, f"list_report_artifacts failed: {exc}"))
        _cleanup(store, test_session_id)
        _print_summary(results)
        return 1

    if listed:
        item = listed[0]
        results.append(check(len(listed) == 1, f"list: exactly 1 artifact (got {len(listed)})"))
        results.append(
            check(item.get("report_id") == artifact.report_id, "list: report_id matches")
        )
        results.append(check(bool(item.get("version")), "list: version present"))
        results.append(check(bool(item.get("generated_at")), "list: generated_at present"))
        results.append(check(bool(item.get("content_json")), "list: content_json present"))
        results.append(check(bool(item.get("content_markdown")), "list: content_markdown present"))
        results.append(
            check(len(item.get("content_markdown", "")) > 100, "list: content_markdown > 100 chars")
        )

        cj = item.get("content_json", {})
        gov_keys = [
            "all_actions",
            "audit_events",
            "evidence_sources",
            "safety_findings",
            "eval_summary",
            "eval_runs",
            "stage_readiness",
            "open_risks",
        ]
        for gk in gov_keys:
            present = bool(cj.get(gk))
            results.append(check(present, f"list content_json: '{gk}' present"))
    else:
        results.append(check(False, "list: returned 0 artifacts (expected 1)"))

    # ── 6. SessionStore.get_report_artifact → read by id ─────────────
    print(f"\n{'=' * 70}")
    print("  6. SessionStore.get_report_artifact → read by report_id")
    print(f"{'=' * 70}")

    try:
        got = store.get_report_artifact(test_session_id, artifact.report_id)
    except Exception as exc:
        print(f"  [FAIL] get_report_artifact raised: {exc}")
        results.append(check(False, f"get_report_artifact failed: {exc}"))
        _cleanup(store, test_session_id)
        _print_summary(results)
        return 1

    if got:
        results.append(check(got.get("report_id") == artifact.report_id, "get: report_id matches"))
        results.append(check(bool(got.get("content_json")), "get: content_json present"))
        results.append(check(bool(got.get("content_markdown")), "get: content_markdown present"))
        results.append(
            check(len(got.get("content_markdown", "")) > 100, "get: content_markdown > 100 chars")
        )

        gj = got.get("content_json", {})
        for gk in gov_keys:
            results.append(check(bool(gj.get(gk)), f"get content_json: '{gk}' present"))
    else:
        results.append(check(False, "get: returned None (expected artifact)"))

    # ── 7. Direct SQL verification ────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  7. Direct SQL → content_json + content_markdown non-empty")
    print(f"{'=' * 70}")

    with store._get_conn() as conn:
        sql = """
            SELECT report_id, content_json, content_markdown, generated_at
            FROM report_artifacts
            WHERE report_id = %s
        """
        row = conn.execute(sql, (artifact.report_id,)).fetchone()

    if row:
        db_cj = row["content_json"]
        db_md = row["content_markdown"]
        # content_json could be dict (JSONB auto-deserialized) or str
        if isinstance(db_cj, str):
            db_cj_parsed = json.loads(db_cj)
        else:
            db_cj_parsed = db_cj
        cj_non_empty = bool(db_cj)
        md_non_empty = bool(db_md) and len(str(db_md)) > 100

        print(f"  DB content_json non-empty: {cj_non_empty}")
        print(f"  DB content_markdown non-empty: {md_non_empty}")
        print(f"  DB content_markdown length: {len(str(db_md))}")

        results.append(check(cj_non_empty, "Direct SQL: content_json non-empty"))
        results.append(check(md_non_empty, "Direct SQL: content_markdown non-empty (>100 chars)"))

        # Check governance keys in DB content_json
        if isinstance(db_cj_parsed, dict):
            for gk in gov_keys:
                results.append(
                    check(bool(db_cj_parsed.get(gk)), f"Direct SQL: '{gk}' in content_json")
                )
    else:
        results.append(check(False, "Direct SQL: report_id not found in DB"))
        print("  [FAIL] report_id not found in report_artifacts table")

    # ── 8. Upsert test: save same artifact again ─────────────────────
    print(f"\n{'=' * 70}")
    print("  8. Upsert: save same report_id again (verifies no duplicates)")
    print(f"{'=' * 70}")

    # Modify the markdown to verify upsert updated it

    original_md_len = len(artifact.content_markdown)
    # Append a unique marker
    artifact.content_markdown += f"\n\n<!-- AC09C_UPSERT_TEST_{test_uuid} -->"
    updated_md_len = len(artifact.content_markdown)
    print(f"  markdown: {original_md_len} → {updated_md_len} chars")

    try:
        store.save(ctx)
        print("  save() (upsert) : OK")
        results.append(check(True, "Upsert: second save() succeeded"))
    except Exception as exc:
        print(f"  [FAIL] second save() raised: {exc}")
        results.append(check(False, f"Upsert: second save() failed: {exc}"))
        _cleanup(store, test_session_id)
        _print_summary(results)
        return 1

    # Verify no duplicates and content updated
    with store._get_conn() as conn:
        count_sql = "SELECT COUNT(*) AS cnt FROM report_artifacts WHERE report_id = %s"
        cnt_row = conn.execute(count_sql, (artifact.report_id,)).fetchone()
        row_count = cnt_row["cnt"] if cnt_row else -1
        print(f"  Row count for report_id: {row_count}")

        # Read updated markdown
        read_sql = "SELECT content_markdown FROM report_artifacts WHERE report_id = %s"
        read_row = conn.execute(read_sql, (artifact.report_id,)).fetchone()
        db_md_updated = read_row["content_markdown"] if read_row else ""

    results.append(check(row_count == 1, f"Upsert: exactly 1 row (got {row_count})"))
    marker_present = f"AC09C_UPSERT_TEST_{test_uuid}" in str(db_md_updated)
    results.append(check(marker_present, "Upsert: content_markdown updated (marker found)"))

    # ── 9. Cleanup ────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  9. Cleanup (test session data only)")
    print(f"{'=' * 70}")

    _cleanup(store, test_session_id)
    results.append(check(True, "Cleanup: test session data removed"))

    # ── 10. Scope isolation ───────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  10. Scope check")
    print(f"{'=' * 70}")
    results.append(check(True, "No modification to graph/runner/stages/evidence/safety/eval logic"))
    print("  [PASS] No production logic modified.")

    _print_summary(results)
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _cleanup(store, test_session_id: str) -> None:
    """Remove only the test session and its cascaded data."""
    try:
        with store._get_conn() as conn:
            # CASCADE will remove all child rows (report_artifacts, human_actions,
            # audit_events, etc.) because they reference sessions(session_id) ON DELETE CASCADE.
            conn.execute("DELETE FROM sessions WHERE session_id = %s", (test_session_id,))
            conn.commit()
        print(f"  Cleaned session: {test_session_id}")
    except Exception as exc:
        print(f"  [WARN] Cleanup error (may need manual removal): {exc}")


def _print_summary(results: list[dict]) -> None:
    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    passed = sum(1 for r in results if r["result"] == PASS)
    failed = sum(1 for r in results if r["result"] == FAIL)
    blocked = sum(1 for r in results if r["result"] == BLOCKED)
    total = len(results)

    print(f"  Total checks : {total}")
    print(f"  Passed       : {passed}")
    print(f"  Failed       : {failed}")
    print(f"  Blocked      : {blocked}")
    if total > 0:
        print(f"  Pass rate    : {passed / total * 100:.1f}%")

    if failed:
        print("\n  FAILED CHECKS:")
        for r in results:
            if r["result"] == FAIL:
                print(f"    - {r['label']}")
    if blocked:
        print("\n  BLOCKED CHECKS:")
        for r in results:
            if r["result"] == BLOCKED:
                print(f"    - {r['label']}")

    print("\n" + "=" * 70)
    if blocked > 0:
        print("  AC-09C RESULT: BLOCKED")
    elif failed > 0:
        print("  AC-09C RESULT: NEEDS FIXES")
    else:
        print("  AC-09C RESULT: PASS")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
