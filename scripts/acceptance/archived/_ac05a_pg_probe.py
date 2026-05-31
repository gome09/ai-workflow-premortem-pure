# _ac05a_pg_probe.py -- AC-05A-R PostgreSQL persistence re-verification probe.
# Exercises formal business logic with PostgreSQL save/load round-trip.
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
    FailureMode,
    FlaggedItem,
    FlagStatus,
    ProjectContext,
    SessionState,
    Stage1Output,
)
from storage.session_store import session_store


def query_table(query: str, params: tuple = ()) -> list[dict]:
    """Direct read-only query against PostgreSQL."""
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(settings.postgres_dsn_sync, row_factory=dict_row) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


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
        print(f"[probe] PostgreSQL connection FAILED: {e}")

    if not pg_available:
        print(
            "\n*** BLOCKING: PostgreSQL not available. Cannot proceed with persistence re-verification. ***"
        )
        sys.exit(1)

    session_store.initialize()
    print("[probe] session_store.initialize(): OK")

    # ── 1. Build an s1_review session and persist via formal save ────────────
    ctx = ProjectContext()
    ctx.research_target = "GPT-4o"
    ctx.domain = "法律文书生成"
    ctx.goal = "提高合同起草准确率"
    ctx.current_state = SessionState.S1_REVIEW

    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="虚构不存在的法律条文",
                severity="high",
                evidence="多份测试报告记录",
                evidence_ids=[],
                needs_verification=False,
            ),
            FailureMode(
                id="FM-002",
                category="上下文遗忘",
                description="长文档中遗漏前置条款约束",
                severity="medium",
                evidence="内部压测结果",
                evidence_ids=[],
                needs_verification=True,
            ),
        ],
        direct_conclusion="GPT-4o 在法律文书领域存在显著幻觉风险。",
        search_sources=[],
        raw_summary="完整原始输出...",
    )
    ctx.flagged_items.append(
        FlaggedItem(
            item_id="FLAG-001",
            stage=1,
            content="AI 输出中【需核验】的法律条文引用可能不准确",
            context="stage_1 raw_summary 第3段",
            status=FlagStatus.PENDING,
        )
    )
    ctx.stage_output_versions["stage_1"] = 1

    # ── 2. Create pending actions via formal oversight service ────────────────
    from core.oversight_service import create_review_actions_for_stage

    created = create_review_actions_for_stage(ctx, 1)
    print(f"[probe] Created {len(created)} PendingHumanAction(s) via formal oversight_service")

    # Save to PostgreSQL BEFORE resolution
    session_store.save(ctx)
    session_id = ctx.session_id
    print(f"[probe] Saved session {session_id} to PostgreSQL")

    # ── 3. Read initial state ──────────────────────────────────────────────────
    initial_pending = ctx.get_pending_actions(stage=1)
    initial_pending_count = len(initial_pending)
    initial_action_types = sorted({str(a.action_type) for a in initial_pending})
    audit_before = len(ctx.audit_events)

    from core.stage_readiness_service import evaluate_stage_gate

    gate_before = evaluate_stage_gate(ctx, 1)
    print(
        f"[probe] Gate before: can_continue={gate_before.can_continue}, blockers={len(gate_before.blockers)}"
    )
    for b in gate_before.blockers:
        print(f"  - [{b.blocker_type}] {b.message[:120]}")

    # ── 4. Resolve exactly one verify_evidence action via formal resolve_action ──
    from core.oversight_service import resolve_action

    verify_actions = [a for a in initial_pending if str(a.action_type) == "verify_evidence"]
    if not verify_actions:
        errors.append("No verify_evidence action found to resolve")
        # fallback to first pending
        target_action = initial_pending[0]
    else:
        target_action = verify_actions[0]

    print(f"\n[probe] Resolving action: {target_action.action_id} type={target_action.action_type}")

    resolved = resolve_action(
        ctx,
        action_id=target_action.action_id,
        decision="verify_evidence",
        note="人工核验通过：该引用已在官方文档中确认。",
    )
    print(f"[probe] Resolved: status={resolved.status} decision={resolved.reviewer_decision}")

    # ── 5. Save after resolution, then reload from PostgreSQL ─────────────────
    session_store.save(ctx)
    print("[probe] Saved after resolution")

    reloaded = session_store.load(session_id)
    if reloaded is None:
        errors.append(f"CRITICAL: session_store.load({session_id}) returned None after save")
        print("\n*** BLOCKING: Failed to reload session from PostgreSQL ***")
        sys.exit(1)

    print(
        f"[probe] Reloaded session {session_id} from PostgreSQL: state={reloaded.current_state.value}"
    )

    # ── 6. Verify reloaded context ────────────────────────────────────────────
    reloaded_pending = reloaded.get_pending_actions(stage=1)
    reloaded_action = next(
        (a for a in reloaded.pending_actions if a.action_id == target_action.action_id),
        None,
    )
    if reloaded_action is None:
        errors.append(f"CRITICAL: Action {target_action.action_id} not found in reloaded context")
    else:
        print(f"[probe] Reloaded action status: {reloaded_action.status}")
        if reloaded_action.status != "resolved":
            errors.append(
                f"Action status in reloaded context is '{reloaded_action.status}', expected 'resolved'"
            )

    audit_after = len(reloaded.audit_events)
    print(f"[probe] Reloaded audit_events count: {audit_after} (before={audit_before})")

    # ── 7. Query independent human_actions table ──────────────────────────────
    ha_rows = query_table(
        "SELECT action_id, action_type, status, reviewer_decision, reviewer_note "
        "FROM human_actions WHERE session_id = %s AND action_id = %s",
        (session_id, target_action.action_id),
    )
    ha_status = ha_rows[0]["status"] if ha_rows else "NOT_FOUND"
    print(f"[probe] human_actions table: action_id={target_action.action_id} status={ha_status}")

    if ha_status != "resolved":
        errors.append(f"human_actions table status is '{ha_status}', expected 'resolved'")

    # ── 8. Query independent audit_events table ───────────────────────────────
    ae_rows = query_table(
        "SELECT event_id, event_type, target_type, target_id "
        "FROM audit_events WHERE session_id = %s AND event_type = 'human_action_resolved'",
        (session_id,),
    )
    has_resolution_event = len(ae_rows) > 0
    print(f"[probe] audit_events table: human_action_resolved events = {len(ae_rows)}")
    for ae in ae_rows:
        print(f"  - {ae['event_id']} {ae['event_type']} target={ae['target_id']}")

    if not has_resolution_event:
        errors.append("audit_events table missing 'human_action_resolved' event")

    # ── 9. Stage Gate after one resolution (on reloaded context) ──────────────
    gate_after = evaluate_stage_gate(reloaded, 1)
    print(
        f"\n[probe] Gate after (on reloaded): can_continue={gate_after.can_continue}, blockers={len(gate_after.blockers)}"
    )
    for b in gate_after.blockers:
        print(f"  - [{b.blocker_type}] {b.message[:120]}")

    # ── 10. Verify final state invariants ─────────────────────────────────────
    final_state = str(reloaded.current_state.value)
    remaining_pending = reloaded.get_pending_actions(stage=1)
    remaining_blocking = [a for a in remaining_pending if a.blocking]
    has_langgraph_interrupt = os.environ.get("WORKFLOW_EXECUTION_MODE") == "langgraph_interrupt"

    print(f"\n[probe] Final state: {final_state}")
    print(
        f"[probe] Remaining pending: {len(remaining_pending)}, blocking: {len(remaining_blocking)}"
    )

    # ── 11. Build JSON report ─────────────────────────────────────────────────
    report = {
        "session_id": session_id,
        "postgres_available": pg_available,
        "initial_state": "s1_review",
        "initial_pending_actions_count": initial_pending_count,
        "stage_gate_before_resolution": {
            "allowed_to_advance": gate_before.can_continue,
            "blockers_count": len(gate_before.blockers),
            "blocker_types": sorted({b.blocker_type for b in gate_before.blockers}),
        },
        "resolved_action": {
            "action_id": target_action.action_id,
            "action_type": str(target_action.action_type),
            "old_status": "pending",
            "new_status": resolved.status,
        },
        "audit_events_before": audit_before,
        "audit_events_after": audit_after,
        "reloaded_from_postgres": reloaded is not None,
        "human_actions_table_status": ha_status,
        "audit_events_table_has_resolution_event": has_resolution_event,
        "stage_gate_after_one_resolution": {
            "allowed_to_advance": gate_after.can_continue,
            "blockers_count": len(gate_after.blockers),
            "blocker_types": sorted({b.blocker_type for b in gate_after.blockers}),
        },
        "final_state": final_state,
        "advanced_to_stage_2": final_state != "s1_review",
        "used_langgraph_interrupt": has_langgraph_interrupt,
    }

    print("\n" + "=" * 60)
    print("AC-05A-R PROBE RESULT (JSON):")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # ── 12. Acceptance assertions ─────────────────────────────────────────────
    if initial_pending_count == 0:
        errors.append("FAIL: No pending actions created")
    if gate_before.can_continue:
        errors.append("FAIL: Stage Gate allowed advancement before any resolution")
    if resolved.status != "resolved":
        errors.append(f"FAIL: Resolved action status is '{resolved.status}', expected 'resolved'")
    if reloaded is None:
        errors.append("FAIL: reloaded context is None")
    if ha_status != "resolved":
        errors.append(f"FAIL: human_actions table status is '{ha_status}', expected 'resolved'")
    if not has_resolution_event:
        errors.append("FAIL: audit_events table missing human_action_resolved event")
    if audit_after <= audit_before:
        errors.append("FAIL: audit_events did not increase")
    if gate_after.can_continue:
        errors.append("FAIL: Gate allowed advancement with remaining blockers")
    if final_state != "s1_review":
        errors.append(f"FAIL: Final state is '{final_state}', expected 's1_review'")

    if errors:
        print("\n*** ACCEPTANCE FAILURES ***")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n*** ACCEPTANCE PASSED: All AC-05A-R criteria satisfied ***")


if __name__ == "__main__":
    main()
