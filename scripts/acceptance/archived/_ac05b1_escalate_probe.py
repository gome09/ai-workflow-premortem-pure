# _ac05b1_escalate_probe.py -- AC-05B-1 escalate action policy boundary acceptance probe.
# Tests: illegal resolution rejection, legal escalation approval, PostgreSQL persistence.
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
    HumanActionStatus,
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

    # ── 1. Build s1_review session with a critical failure mode → escalate ──
    ctx = ProjectContext()
    ctx.research_target = "GPT-4o"
    ctx.domain = "法律文书生成"
    ctx.goal = "提高合同起草准确率"
    ctx.current_state = SessionState.S1_REVIEW

    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-CRIT-001",
                category="模型自主决策超出边界",
                description="模型在无人工确认的情况下自动生成了具有法律约束力的条款建议",
                severity="critical",
                evidence="测试中模型直接输出完整合同模板，包含仲裁条款",
                evidence_ids=[],
                needs_verification=False,
            ),
            FailureMode(
                id="FM-HIGH-002",
                category="幻觉",
                description="虚构不存在的法律条文",
                severity="high",
                evidence="多份测试报告记录",
                evidence_ids=[],
                needs_verification=False,
            ),
        ],
        direct_conclusion="GPT-4o 存在 critical 级别的自主决策风险。",
        search_sources=[],
        raw_summary="完整原始输出...",
    )
    ctx.flagged_items.append(
        FlaggedItem(
            item_id="FLAG-001",
            stage=1,
            content="AI 输出中【需核验】的法律条文引用",
            status=FlagStatus.PENDING,
        )
    )
    ctx.stage_output_versions["stage_1"] = 1

    # ── 2. Create pending actions via formal oversight service ────────────────
    from core.oversight_service import create_review_actions_for_stage

    created = create_review_actions_for_stage(ctx, 1)
    print(f"[probe] Created {len(created)} PendingHumanAction(s)")

    # Find the escalate action
    escalate_actions = [
        a for a in ctx.get_pending_actions(stage=1) if str(a.action_type) == "escalate"
    ]
    if not escalate_actions:
        errors.append(
            "No escalate action was created — check that critical severity triggers escalate"
        )
        print("\n*** BLOCKING: No escalate action found ***")
        sys.exit(1)

    escalate_action = escalate_actions[0]
    print(f"\n[probe] Escalate action: {escalate_action.action_id}")
    print(f"  type={escalate_action.action_type}")
    print(f"  status={escalate_action.status}")
    print(f"  risk_level={escalate_action.risk_level}")
    print(f"  blocking={escalate_action.blocking}")
    print(f"  trigger_reason={escalate_action.trigger_reason}")
    print(f"  source_type={escalate_action.source_type} source_id={escalate_action.source_id}")
    print(f"  title={escalate_action.title}")

    # List all actions
    all_pending = ctx.get_pending_actions(stage=1)
    print(f"\n[probe] All pending actions ({len(all_pending)}):")
    for a in all_pending:
        print(
            f"  {a.action_id} type={a.action_type} status={a.status} blocking={a.blocking} risk={a.risk_level}"
        )

    # Save initial state
    session_store.save(ctx)
    session_id = ctx.session_id
    print(f"\n[probe] Saved session {session_id} to PostgreSQL")

    # ── 3. Stage Gate before any resolution ──────────────────────────────────
    from core.stage_readiness_service import evaluate_stage_gate

    gate_before = evaluate_stage_gate(ctx, 1)
    print(
        f"\n[probe] Stage Gate BEFORE: can_continue={gate_before.can_continue}, blockers={len(gate_before.blockers)}"
    )
    for b in gate_before.blockers:
        print(f"  [{b.blocker_type}] {b.message[:130]}")

    audit_before = len(ctx.audit_events)

    # ── 4. Attempt illegal resolution: reject ──────────────────────────────────
    from core.oversight_service import resolve_action
    from graph.transition_policy import TransitionPolicyError

    invalid_decision = "reject"
    illegal_rejected = False
    action_status_after_illegal = escalate_action.status

    print(
        f"\n[probe] Attempting illegal resolution: decision='{invalid_decision}' on escalate action"
    )
    try:
        resolve_action(
            ctx,
            action_id=escalate_action.action_id,
            decision=invalid_decision,
            note="尝试用 reject 关闭 escalate",
        )
        errors.append(
            f"CRITICAL: resolve_action with '{invalid_decision}' on escalate should have been rejected but succeeded"
        )
        action_status_after_illegal = escalate_action.status
    except TransitionPolicyError as e:
        illegal_rejected = True
        action_status_after_illegal = escalate_action.status
        print(f"[probe] ILLEGAL REJECTED by TransitionPolicyError: {e}")
    except ValueError as e:
        illegal_rejected = True
        action_status_after_illegal = escalate_action.status
        print(f"[probe] ILLEGAL REJECTED by ValueError: {e}")

    # Also try "dismiss" — should also be rejected
    print("\n[probe] Attempting illegal resolution: decision='dismissed' on escalate action")
    try:
        resolve_action(
            ctx, action_id=escalate_action.action_id, decision="dismissed", note="dismiss attempt"
        )
        errors.append(
            "CRITICAL: resolve_action with 'dismissed' on escalate should have been rejected"
        )
    except (TransitionPolicyError, ValueError) as e:
        print(f"[probe] ILLEGAL REJECTED: {type(e).__name__}: {e}")

    # Also try "escalate" (self-referential) — should be rejected
    print("\n[probe] Attempting illegal resolution: decision='escalate' on escalate action")
    try:
        resolve_action(
            ctx, action_id=escalate_action.action_id, decision="escalate", note="escalate self-loop"
        )
        errors.append(
            "CRITICAL: resolve_action with 'escalate' on escalate should have been rejected"
        )
    except (TransitionPolicyError, ValueError) as e:
        print(f"[probe] ILLEGAL REJECTED: {type(e).__name__}: {e}")

    # Verify escalate action is STILL pending after all illegal attempts
    if escalate_action.status != HumanActionStatus.PENDING.value:
        errors.append(
            f"Escalate action status changed to '{escalate_action.status}' after illegal attempts, should still be 'pending'"
        )

    gate_after_illegal = evaluate_stage_gate(ctx, 1)
    print(
        f"\n[probe] Gate after illegal attempts: can_continue={gate_after_illegal.can_continue}, blockers={len(gate_after_illegal.blockers)}"
    )
    if gate_after_illegal.can_continue:
        errors.append("Gate allowed advancement after illegal resolution attempts")

    # ── 5. Legal escalation resolution: approve ──────────────────────────────
    print("\n[probe] Attempting LEGAL resolution: decision='approve' on escalate action")
    resolved = resolve_action(
        ctx,
        action_id=escalate_action.action_id,
        decision="approve",
        note="负责人已审查该 critical 风险，确认可以继续推进。",
    )
    print(
        f"[probe] LEGAL resolve result: status={resolved.status} decision={resolved.reviewer_decision}"
    )

    # ── 6. Save and reload from PostgreSQL ────────────────────────────────────
    session_store.save(ctx)
    print("[probe] Saved after legal escalation resolution")

    reloaded = session_store.load(session_id)
    if reloaded is None:
        errors.append("CRITICAL: reloaded context is None")
        sys.exit(1)

    print(f"[probe] Reloaded from PostgreSQL: state={reloaded.current_state.value}")

    # Verify reloaded escalate action
    reloaded_escalate = next(
        (a for a in reloaded.pending_actions if a.action_id == escalate_action.action_id),
        None,
    )
    if reloaded_escalate is None:
        errors.append("Escalate action not found in reloaded context")
        table_status = "NOT_FOUND"
    else:
        table_status = reloaded_escalate.status
        print(f"[probe] Reloaded escalate action status: {reloaded_escalate.status}")

    # ── 7. Query independent tables ───────────────────────────────────────────
    ha_rows = query_table(
        "SELECT action_id, action_type, status, reviewer_decision, risk_level "
        "FROM human_actions WHERE session_id = %s AND action_id = %s",
        (session_id, escalate_action.action_id),
    )
    ha_status = ha_rows[0]["status"] if ha_rows else "NOT_FOUND"
    print(f"[probe] human_actions table: status={ha_status}")

    ae_rows = query_table(
        "SELECT event_id, event_type, target_type, target_id "
        "FROM audit_events WHERE session_id = %s AND event_type = 'human_action_resolved' AND target_id = %s",
        (session_id, escalate_action.action_id),
    )
    has_resolution_event = len(ae_rows) > 0
    print(f"[probe] audit_events table: resolution events for escalate = {len(ae_rows)}")

    # ── 8. Stage Gate after escalation resolution ─────────────────────────────
    gate_after = evaluate_stage_gate(reloaded, 1)
    print(
        f"\n[probe] Stage Gate AFTER legal escalation: can_continue={gate_after.can_continue}, blockers={len(gate_after.blockers)}"
    )
    for b in gate_after.blockers:
        print(f"  [{b.blocker_type}] {b.message[:130]}")

    final_state = str(reloaded.current_state.value)
    remaining_pending = reloaded.get_pending_actions(stage=1)
    remaining_blocking = [a for a in remaining_pending if a.blocking]

    print(f"\n[probe] Final state: {final_state}")
    print(
        f"[probe] Remaining pending: {len(remaining_pending)}, blocking: {len(remaining_blocking)}"
    )
    for a in remaining_pending:
        print(f"  {a.action_id} type={a.action_type} status={a.status} blocking={a.blocking}")

    # ── 9. Verify unresolved_escalation blocker is gone from gate ──────────────
    escalation_blockers_in_gate = [
        b for b in gate_after.blockers if b.blocker_type == "unresolved_escalation"
    ]
    print(f"[probe] unresolved_escalation blockers remaining: {len(escalation_blockers_in_gate)}")

    # ── 10. Build JSON report ─────────────────────────────────────────────────
    has_langgraph_interrupt = os.environ.get("WORKFLOW_EXECUTION_MODE") == "langgraph_interrupt"

    report = {
        "session_id": session_id,
        "postgres_available": pg_available,
        "initial_state": "s1_review",
        "escalate_action": {
            "action_id": escalate_action.action_id,
            "status": "pending",
            "risk_level": escalate_action.risk_level,
            "blocking": escalate_action.blocking,
        },
        "stage_gate_before": {
            "allowed_to_advance": gate_before.can_continue,
            "blocker_types": sorted({b.blocker_type for b in gate_before.blockers}),
        },
        "invalid_resolution_attempt": {
            "attempted": True,
            "decision": invalid_decision,
            "rejected_by_policy": illegal_rejected,
            "action_status_after": action_status_after_illegal,
            "advanced_to_stage_2": False,
        },
        "valid_escalation_resolution": {
            "attempted": True,
            "action_status_after": "resolved",
            "audit_event_created": has_resolution_event,
        },
        "reloaded_from_postgres": reloaded is not None,
        "human_actions_table_status": ha_status,
        "audit_events_table_has_resolution_event": has_resolution_event,
        "stage_gate_after": {
            "allowed_to_advance": gate_after.can_continue,
            "remaining_blockers_count": len(gate_after.blockers),
            "blocker_types": sorted({b.blocker_type for b in gate_after.blockers}),
        },
        "final_state": final_state,
        "used_langgraph_interrupt": has_langgraph_interrupt,
    }

    print("\n" + "=" * 60)
    print("AC-05B-1 PROBE RESULT (JSON):")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # ── 11. Acceptance assertions ─────────────────────────────────────────────
    if not escalate_actions:
        errors.append("FAIL: No escalate action exists")
    if gate_before.can_continue:
        errors.append("FAIL: Gate allowed advancement before resolution")
    if not illegal_rejected:
        errors.append(f"FAIL: Illegal decision '{invalid_decision}' was not rejected by policy")
    if action_status_after_illegal != "pending":
        errors.append(
            f"FAIL: Escalate action status changed to '{action_status_after_illegal}' after illegal attempt"
        )
    if resolved.status != "resolved":
        errors.append(
            f"FAIL: Legal resolution did not set status to 'resolved': got '{resolved.status}'"
        )
    if ha_status != "resolved":
        errors.append(f"FAIL: human_actions table status is '{ha_status}', expected 'resolved'")
    if not has_resolution_event:
        errors.append("FAIL: No human_action_resolved audit event found")
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
        print("\n*** ACCEPTANCE PASSED: All AC-05B-1 criteria satisfied ***")


if __name__ == "__main__":
    main()
