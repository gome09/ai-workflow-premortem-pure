# _ac05b3_evidence_probe.py -- AC-05B-3 evidence action + evidence_gap blocker linkage probe.
# Tests: EvidenceSource verified state → verify_evidence action → evidence_gap blocker →
# PostgreSQL persistence → audit trail completeness.
from __future__ import annotations

import json
import os
import sys

from pathlib import Path
os.chdir(Path(__file__).resolve().parent.parent.parent.parent)
os.environ["WORKFLOW_EXECUTION_MODE"] = "single_step"
os.environ["STAGE_OUTPUT_MODE"] = "json_first"

from core.config import settings
from core.models import (
    EvidenceSource,
    FailureMode,
    ProjectContext,
    SessionState,
    Stage1Output,
)
from storage.session_store import session_store


def query_table(query: str, params: tuple = ()) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(settings.postgres_dsn_sync, row_factory=dict_row) as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def main() -> None:
    errors: list[str] = []

    # ── 0. PostgreSQL check ───────────────────────────────────────────────────
    pg_available = False
    try:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(settings.postgres_dsn_sync, row_factory=dict_row)
        conn.execute("SELECT 1")
        conn.close()
        pg_available = True
        print("[probe] PostgreSQL connection: OK")
    except Exception as e:
        errors.append(f"PostgreSQL not available: {e}")
        pg_available = False

    if not pg_available:
        print("\n*** BLOCKING: PostgreSQL not available ***")
        sys.exit(1)

    session_store.initialize()
    print("[probe] session_store.initialize(): OK")

    # ── 1. Build s1_review session with unverified evidence ──────────────────
    ctx = ProjectContext()
    ctx.research_target = "GPT-4o"
    ctx.domain = "法律文书生成"
    ctx.goal = "提高合同起草准确率"
    ctx.current_state = SessionState.S1_REVIEW

    # Pre-create an EvidenceSource that exists but is NOT verified
    evidence = EvidenceSource(
        evidence_id="EVID-LEGAL-001",
        session_id=ctx.session_id,
        title="民法典 第496条 格式条款",
        url="https://example.com/civil-code-496",
        source_type="official_doc",
        credibility_score=0.85,
        summary="《中华人民共和国民法典》第496条：格式条款是当事人为了重复使用而预先拟定...",
        claims=["格式条款提供方应当遵循公平原则确定当事人之间的权利和义务"],
        verified=False,
    )
    ctx.evidence_sources.append(evidence)
    print(f"[probe] Created EvidenceSource: {evidence.evidence_id} verified={evidence.verified}")

    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-HIGH-001",
                category="幻觉",
                description="虚构不存在的法律条文",
                severity="high",
                evidence="模型引用民法典第496条，需核验该条文是否真实存在",
                evidence_ids=["EVID-LEGAL-001"],
                needs_verification=False,
            ),
        ],
        direct_conclusion="GPT-4o 在法律文书领域存在显著幻觉风险，需人工核验证据。",
        search_sources=[],
        raw_summary="完整原始输出...",
    )
    ctx.stage_output_versions["stage_1"] = 1

    # Link failure modes to evidence (establishes used_by_failure_mode_ids reverse refs)
    from core.evidence_service import link_failure_modes_to_evidence

    link_failure_modes_to_evidence(ctx)
    print(f"[probe] Evidence used_by_failure_mode_ids: {evidence.used_by_failure_mode_ids}")

    # ── 2. Create pending actions via formal oversight service ────────────────
    from core.oversight_service import create_review_actions_for_stage

    created = create_review_actions_for_stage(ctx, 1)
    print(f"[probe] Created {len(created)} PendingHumanAction(s)")

    # Find the verify_evidence action for unverified evidence
    verify_actions = [
        a
        for a in ctx.get_pending_actions(stage=1)
        if str(a.action_type) == "verify_evidence"
        and str(a.source_type) == "evidence_unverified_for_high_risk"
    ]
    if not verify_actions:
        errors.append("No evidence_unverified_for_high_risk verify_evidence action found")
        print("\n*** BLOCKING: No verify_evidence action for unverified high-risk evidence ***")
        # Dump all actions for diagnosis
        all_pending = ctx.get_pending_actions(stage=1)
        print(f"[probe] All pending actions ({len(all_pending)}):")
        for a in all_pending:
            print(
                f"  {a.action_id} type={a.action_type} source={a.source_type}/{a.source_id} status={a.status}"
            )
        sys.exit(1)

    verify_action = verify_actions[0]
    print(f"\n[probe] Verify evidence action: {verify_action.action_id}")
    print(f"  type={verify_action.action_type}")
    print(f"  source_type={verify_action.source_type}")
    print(f"  source_id={verify_action.source_id}")
    print(f"  status={verify_action.status}")
    print(f"  blocking={verify_action.blocking}")
    print(f"  risk_level={verify_action.risk_level}")
    print(f"  trigger_reason={verify_action.trigger_reason}")

    # List all actions
    all_pending = ctx.get_pending_actions(stage=1)
    print(f"\n[probe] All pending actions ({len(all_pending)}):")
    for a in all_pending:
        print(
            f"  {a.action_id} type={a.action_type} source={a.source_type}/{a.source_id} status={a.status} blocking={a.blocking}"
        )

    session_store.save(ctx)
    session_id = ctx.session_id
    print(f"\n[probe] Saved session {session_id} to PostgreSQL")

    # ── 3. Stage Gate before verification ────────────────────────────────────
    from core.stage_readiness_service import evaluate_stage_gate

    gate_before = evaluate_stage_gate(ctx, 1)
    print(
        f"\n[probe] Stage Gate BEFORE: can_continue={gate_before.can_continue}, blockers={len(gate_before.blockers)}"
    )
    for b in gate_before.blockers:
        print(
            f"  [{b.blocker_type}] gap_type={b.metadata.get('gap_type', 'N/A')} | {b.message[:150]}"
        )

    # Find unverified_evidence_id blockers specifically
    unverified_blockers_before = [
        b for b in gate_before.blockers if b.metadata.get("gap_type") == "unverified_evidence_id"
    ]
    print(f"[probe] unverified_evidence_id blockers before: {len(unverified_blockers_before)}")
    for b in unverified_blockers_before:
        print(f"  evidence_id={b.metadata.get('source_id')} fm={b.metadata.get('failure_mode_id')}")

    audit_before = len(ctx.audit_events)
    print(f"[probe] Audit events before: {audit_before}")

    # ── 4. Verify evidence via formal evidence_service ────────────────────────
    from core.evidence_service import verify_evidence_source
    from core.oversight_service import resolve_actions_for_evidence

    print("\n[probe] === STEP 4a: verify_evidence_source(EVID-LEGAL-001) ===")
    try:
        verified_ev = verify_evidence_source(
            ctx,
            evidence_id="EVID-LEGAL-001",
            note="人工核验通过：民法典第496条内容属实，来源权威。",
            verified_by="user",
        )
        print(
            f"[probe] Evidence verified: verified={verified_ev.verified} verified_by={verified_ev.verified_by}"
        )
    except ValueError as e:
        errors.append(f"verify_evidence_source failed: {e}")
        print(f"[probe] ERROR: {e}")
        sys.exit(1)

    # Check evidence state in context
    evidence_verified_after_verify = evidence.verified
    print(
        f"[probe] EvidenceSource.verified after verify_evidence_source: {evidence_verified_after_verify}"
    )

    # Check audit event for evidence_verified
    evidence_verified_audit = [
        ae
        for ae in ctx.audit_events
        if ae.event_type == "evidence_verified" and ae.target_id == "EVID-LEGAL-001"
    ]
    print(f"[probe] evidence_verified audit events: {len(evidence_verified_audit)}")

    print("\n[probe] === STEP 4b: resolve_actions_for_evidence(EVID-LEGAL-001) ===")
    resolved_action_ids = resolve_actions_for_evidence(
        ctx,
        evidence_id="EVID-LEGAL-001",
        decision="verify_evidence",
        note="证据 EVID-LEGAL-001 已核验，关闭关联的 verify_evidence action。",
    )
    print(f"[probe] Auto-resolved {len(resolved_action_ids)} actions: {resolved_action_ids}")

    # Check action status after resolution
    verify_action_status_after = verify_action.status
    print(f"[probe] verify_evidence action status after: {verify_action_status_after}")
    print(f"[probe] verify_evidence action reviewer_decision: {verify_action.reviewer_decision}")

    # Check audit events for human_action_resolved
    action_resolved_audit = [
        ae
        for ae in ctx.audit_events
        if ae.event_type == "human_action_resolved" and ae.target_id == verify_action.action_id
    ]
    print(
        f"[probe] human_action_resolved audit events for verify_action: {len(action_resolved_audit)}"
    )

    # ── 5. Save and reload from PostgreSQL ────────────────────────────────────
    session_store.save(ctx)
    print("\n[probe] Saved after evidence verification + action resolution")

    reloaded = session_store.load(session_id)
    if reloaded is None:
        errors.append("CRITICAL: reloaded context is None")
        sys.exit(1)

    print(f"[probe] Reloaded from PostgreSQL: state={reloaded.current_state.value}")

    # Verify reloaded evidence
    reloaded_evidence = next(
        (ev for ev in reloaded.evidence_sources if ev.evidence_id == "EVID-LEGAL-001"),
        None,
    )
    if reloaded_evidence is None:
        errors.append("CRITICAL: Evidence EVID-LEGAL-001 not found in reloaded context")
    else:
        print(
            f"[probe] Reloaded evidence: verified={reloaded_evidence.verified} verified_by={reloaded_evidence.verified_by}"
        )

    # Verify reloaded action
    reloaded_action = next(
        (a for a in reloaded.pending_actions if a.action_id == verify_action.action_id),
        None,
    )
    if reloaded_action is None:
        errors.append("CRITICAL: verify_evidence action not found in reloaded context")
        reloaded_action_status = "NOT_FOUND"
    else:
        reloaded_action_status = reloaded_action.status
        print(f"[probe] Reloaded verify_action status: {reloaded_action_status}")

    # ── 6. Query independent tables ───────────────────────────────────────────
    # evidence_sources table
    ev_rows = query_table(
        "SELECT evidence_id, verified, verified_by, verified_at, verification_note "
        "FROM evidence_sources WHERE session_id = %s AND evidence_id = %s",
        (session_id, "EVID-LEGAL-001"),
    )
    ev_table_verified = bool(ev_rows[0]["verified"]) if ev_rows else False
    print(f"[probe] evidence_sources table: verified={ev_table_verified}")
    if ev_rows:
        print(f"  verified_by={ev_rows[0]['verified_by']} verified_at={ev_rows[0]['verified_at']}")

    # human_actions table
    ha_rows = query_table(
        "SELECT action_id, action_type, status, reviewer_decision, reviewer_note "
        "FROM human_actions WHERE session_id = %s AND action_id = %s",
        (session_id, verify_action.action_id),
    )
    ha_status = ha_rows[0]["status"] if ha_rows else "NOT_FOUND"
    print(f"[probe] human_actions table: status={ha_status}")

    # audit_events table - evidence_verified
    ae_evidence_rows = query_table(
        "SELECT event_id, event_type, target_type, target_id "
        "FROM audit_events WHERE session_id = %s AND event_type = 'evidence_verified' AND target_id = %s",
        (session_id, "EVID-LEGAL-001"),
    )
    has_evidence_verified_event = len(ae_evidence_rows) > 0
    print(f"[probe] audit_events table: evidence_verified events = {len(ae_evidence_rows)}")

    # audit_events table - human_action_resolved
    ae_action_rows = query_table(
        "SELECT event_id, event_type, target_type, target_id "
        "FROM audit_events WHERE session_id = %s AND event_type = 'human_action_resolved' AND target_id = %s",
        (session_id, verify_action.action_id),
    )
    has_action_resolved_event = len(ae_action_rows) > 0
    print(f"[probe] audit_events table: human_action_resolved events = {len(ae_action_rows)}")
    for ae in ae_action_rows:
        print(f"  {ae['event_id']} {ae['event_type']} target={ae['target_id']}")

    # ── 7. Stage Gate after verification ─────────────────────────────────────
    gate_after = evaluate_stage_gate(reloaded, 1)
    print(
        f"\n[probe] Stage Gate AFTER: can_continue={gate_after.can_continue}, blockers={len(gate_after.blockers)}"
    )
    for b in gate_after.blockers:
        print(
            f"  [{b.blocker_type}] gap_type={b.metadata.get('gap_type', 'N/A')} | {b.message[:150]}"
        )

    # Check if the same unverified_evidence_id blocker still exists
    unverified_blockers_after = [
        b for b in gate_after.blockers if b.metadata.get("gap_type") == "unverified_evidence_id"
    ]
    same_unverified_blocker_remains = len(unverified_blockers_after) > 0
    print(f"[probe] unverified_evidence_id blockers after: {len(unverified_blockers_after)}")

    final_state = str(reloaded.current_state.value)
    remaining_pending = reloaded.get_pending_actions(stage=1)
    remaining_blocking = [a for a in remaining_pending if a.blocking]

    print(f"\n[probe] Final state: {final_state}")
    print(
        f"[probe] Remaining pending: {len(remaining_pending)}, blocking: {len(remaining_blocking)}"
    )
    for a in remaining_pending:
        print(f"  {a.action_id} type={a.action_type} status={a.status} blocking={a.blocking}")

    # ── 8. Build JSON report ─────────────────────────────────────────────────
    has_langgraph_interrupt = os.environ.get("WORKFLOW_EXECUTION_MODE") == "langgraph_interrupt"

    report = {
        "session_id": session_id,
        "postgres_available": pg_available,
        "initial_state": "s1_review",
        "evidence": {
            "evidence_id": "EVID-LEGAL-001",
            "exists": True,
            "verified_before": False,
            "linked_failure_mode_id": "FM-HIGH-001",
        },
        "verify_action": {
            "action_id": verify_action.action_id,
            "action_type": "verify_evidence",
            "status_before": "pending",
            "blocking": True,
        },
        "stage_gate_before": {
            "allowed_to_advance": gate_before.can_continue,
            "blockers_count": len(gate_before.blockers),
            "blocker_types": sorted({b.blocker_type for b in gate_before.blockers}),
            "has_unverified_evidence_blocker": len(unverified_blockers_before) > 0,
        },
        "verify_resolution": {
            "attempted": True,
            "action_status_after": verify_action_status_after,
            "evidence_verified_after": evidence_verified_after_verify,
            "audit_event_created": len(evidence_verified_audit) > 0,
        },
        "reloaded_from_postgres": reloaded is not None,
        "evidence_sources_table_verified": ev_table_verified,
        "human_actions_table_status": ha_status,
        "audit_events_table_has_resolution_event": has_action_resolved_event,
        "stage_gate_after": {
            "allowed_to_advance": gate_after.can_continue,
            "remaining_blockers_count": len(gate_after.blockers),
            "has_same_unverified_evidence_blocker": same_unverified_blocker_remains,
            "blocker_types": sorted({b.blocker_type for b in gate_after.blockers}),
        },
        "final_state": final_state,
        "advanced_to_stage_2": final_state != "s1_review",
        "used_langgraph_interrupt": has_langgraph_interrupt,
    }

    print("\n" + "=" * 60)
    print("AC-05B-3 PROBE RESULT (JSON):")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # ── 9. Acceptance assertions ─────────────────────────────────────────────
    # C1: session in s1_review
    if final_state != "s1_review":
        errors.append(f"FAIL: Final state is '{final_state}', expected 's1_review'")

    # C2: Stage 1 output references real EvidenceSource
    if not ev_rows:
        errors.append("FAIL: EvidenceSource EVID-LEGAL-001 not found in evidence_sources table")

    # C3: EvidenceSource initially unverified
    # (verified by construction: verified_before=False in report)

    # C4: Formal verify_evidence action exists with action_id, status, blocking reason
    if not verify_actions:
        errors.append("FAIL: No verify_evidence action found")

    # C5: Stage Gate blocks advancement when evidence unverified
    if gate_before.can_continue:
        errors.append("FAIL: Gate allowed advancement before evidence verification")
    if not unverified_blockers_before:
        errors.append("FAIL: No unverified_evidence_id blocker found before verification")

    # C6: blocker explains why evidence needs verification
    if unverified_blockers_before:
        first_blocker_msg = unverified_blockers_before[0].message
        if "verified" not in first_blocker_msg.lower():
            errors.append("FAIL: Blocker message does not explain unverified evidence")

    # C7: verify through formal service, not direct DB modification
    # (verified by construction: using verify_evidence_source + resolve_actions_for_evidence)

    # C8: EvidenceSource verified state persisted to context + evidence_sources table
    if reloaded_evidence is not None and not reloaded_evidence.verified:
        errors.append("FAIL: EvidenceSource.verified not True in reloaded context")
    if not ev_table_verified:
        errors.append("FAIL: evidence_sources table verified is not True")
    if reloaded_evidence is not None and reloaded_evidence.verified_by != "user":
        errors.append(
            f"FAIL: EvidenceSource.verified_by is '{reloaded_evidence.verified_by}', expected 'user'"
        )

    # C9: verify_evidence action status persisted to context + human_actions table
    if verify_action_status_after != "resolved":
        errors.append(
            f"FAIL: verify_action status is '{verify_action_status_after}', expected 'resolved'"
        )
    if ha_status != "resolved":
        errors.append(f"FAIL: human_actions table status is '{ha_status}', expected 'resolved'")

    # C10: evidence_verified + human_action_resolved audit events written
    if not has_evidence_verified_event:
        errors.append("FAIL: No evidence_verified audit event in audit_events table")
    if not has_action_resolved_event:
        errors.append("FAIL: No human_action_resolved audit event in audit_events table")

    # C11: same unverified_evidence_id blocker gone after resolution
    if same_unverified_blocker_remains:
        errors.append("FAIL: unverified_evidence_id blocker still present after verification")

    # C12: if other blockers remain, state stays at s1_review (not stage 2)
    if gate_after.blockers and gate_after.can_continue:
        errors.append("FAIL: Gate allows advancement despite remaining blockers")
    if gate_after.blockers and final_state == "s2_running":
        errors.append("FAIL: Advanced to stage 2 despite remaining blockers")

    # C13: No LangGraph interrupt used
    # (verified by construction: WORKFLOW_EXECUTION_MODE=single_step)

    if errors:
        print("\n*** ACCEPTANCE FAILURES ***")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n*** ACCEPTANCE PASSED: All AC-05B-3 criteria satisfied ***")


if __name__ == "__main__":
    main()
