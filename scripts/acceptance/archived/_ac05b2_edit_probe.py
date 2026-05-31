# _ac05b2_edit_probe.py -- AC-05B-2 edit action + payload_after structured validation probe.
# Tests: no-payload rejection, incomplete-payload rejection, valid structured edit,
# PostgreSQL persistence, Stage Gate re-evaluation.
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

    # ── 1. Build s1_review session with failure modes lacking evidence_ids ──
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
                evidence="测试中模型直接输出完整合同模板",
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
        direct_conclusion="GPT-4o 在领域存在显著风险。",
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

    # Find an evidence_gap edit action (these require structured payload_after)
    evidence_gap_edits = [
        a
        for a in ctx.get_pending_actions(stage=1)
        if str(a.action_type) == "edit" and str(a.source_type) == "evidence_gap"
    ]
    if not evidence_gap_edits:
        errors.append("No evidence_gap edit action found")
        print("\n*** BLOCKING: No evidence_gap edit action ***")
        sys.exit(1)

    edit_action = evidence_gap_edits[0]
    requires_structured = str(edit_action.source_type) in {
        "parser",
        "policy_gap",
        "evidence_gap",
        "eval_coverage",
    }

    print(f"\n[probe] Edit action: {edit_action.action_id}")
    print(f"  type={edit_action.action_type}")
    print(f"  status={edit_action.status}")
    print(f"  source_type={edit_action.source_type}")
    print(f"  source_id={edit_action.source_id}")
    print(f"  blocking={edit_action.blocking}")
    print(f"  risk_level={edit_action.risk_level}")
    print(f"  trigger_reason={edit_action.trigger_reason}")
    print(f"  requires_structured_output={requires_structured}")
    print(f"  title={edit_action.title}")

    # List all actions before resolution
    all_pending = ctx.get_pending_actions(stage=1)
    print(f"\n[probe] All pending actions ({len(all_pending)}):")
    for a in all_pending:
        print(
            f"  {a.action_id} type={a.action_type} source={a.source_type}/{a.source_id} status={a.status}"
        )

    session_store.save(ctx)
    session_id = ctx.session_id
    print(f"\n[probe] Saved session {session_id} to PostgreSQL")

    # ── 3. Stage Gate before any resolution ───────────────────────────────────
    from core.stage_readiness_service import evaluate_stage_gate

    gate_before = evaluate_stage_gate(ctx, 1)
    print(
        f"\n[probe] Stage Gate BEFORE: can_continue={gate_before.can_continue}, blockers={len(gate_before.blockers)}"
    )
    for b in gate_before.blockers:
        print(f"  [{b.blocker_type}] {b.message[:140]}")

    audit_before = len(ctx.audit_events)
    print(f"\n[probe] Audit events before: {audit_before}")

    # ── 4. Attempt illegal: resolve edit WITHOUT payload_after ──────────────
    from core.oversight_service import resolve_action
    from graph.transition_policy import TransitionPolicyError

    print("\n[probe] === ATTEMPT 1: resolve edit WITHOUT payload_after ===")
    illegal_no_payload_rejected = False
    try:
        resolve_action(
            ctx,
            action_id=edit_action.action_id,
            decision="edit",
            note="尝试无 payload_after 关闭 edit",
            payload_after=None,
        )
        errors.append("CRITICAL: edit resolve WITHOUT payload_after should have been rejected")
    except TransitionPolicyError as e:
        illegal_no_payload_rejected = True
        print(f"[probe] REJECTED by TransitionPolicyError: {e}")
    except ValueError as e:
        illegal_no_payload_rejected = True
        print(f"[probe] REJECTED by ValueError: {e}")

    status_after_no_payload = edit_action.status
    print(f"[probe] Action status after: {status_after_no_payload}")

    # ── 5. Attempt illegal: resolve edit with INCOMPLETE payload_after ──────
    print("\n[probe] === ATTEMPT 2: resolve edit with INCOMPLETE payload_after ===")
    illegal_incomplete_rejected = False
    try:
        resolve_action(
            ctx,
            action_id=edit_action.action_id,
            decision="edit",
            note="尝试用不完整 payload 关闭 edit",
            payload_after={"note": "edited", "comment": "just adding notes, no structured_output"},
        )
        errors.append(
            "CRITICAL: edit resolve with incomplete payload_after should have been rejected"
        )
    except TransitionPolicyError as e:
        illegal_incomplete_rejected = True
        print(f"[probe] REJECTED by TransitionPolicyError: {e}")
    except ValueError as e:
        illegal_incomplete_rejected = True
        print(f"[probe] REJECTED by ValueError: {e}")

    status_after_incomplete = edit_action.status
    print(f"[probe] Action status after: {status_after_incomplete}")

    # Verify gate hasn't changed after illegal attempts
    gate_after_illegal = evaluate_stage_gate(ctx, 1)
    print(
        f"[probe] Gate after illegal attempts: can_continue={gate_after_illegal.can_continue}, blockers={len(gate_after_illegal.blockers)}"
    )
    if gate_after_illegal.can_continue:
        errors.append("Gate allowed advancement after illegal resolution attempts")

    # Verify no fake audit events were created
    audit_after_illegal = len(ctx.audit_events)
    has_fake_resolution = any(
        ae.event_type == "human_action_resolved" and ae.target_id == edit_action.action_id
        for ae in ctx.audit_events
    )
    if has_fake_resolution:
        errors.append(
            "CRITICAL: Fake human_action_resolved audit event found after illegal attempts"
        )
    print(
        f"[probe] Audit events after illegal attempts: {audit_after_illegal} (no fake resolution: {not has_fake_resolution})"
    )

    # ── 6. Legal structured edit ────────────────────────────────────────────
    print("\n[probe] === ATTEMPT 3: LEGAL structured edit with valid payload_after ===")

    # Build a valid payload_after with failure_modes (Stage 1 schema)
    # Preserve all existing failure modes, add evidence_ids to fix FM-HIGH-002 gap
    valid_payload = {
        "failure_modes": [
            {
                "id": "FM-CRIT-001",
                "category": "模型自主决策超出边界",
                "description": "模型在无人工确认的情况下自动生成了具有法律约束力的条款建议",
                "severity": "critical",
                "evidence_ids": [],
                "evidence": "测试中模型直接输出完整合同模板",
            },
            {
                "id": "FM-HIGH-002",
                "category": "幻觉",
                "description": "虚构不存在的法律条文",
                "severity": "high",
                "evidence_ids": ["EVID-001"],
                "evidence": "多份测试报告记录，补充引用 EVID-001",
            },
        ],
        "direct_conclusion": "GPT-4o 在领域存在显著风险，已补充证据引用。",
    }

    print("[probe] Submitting valid payload with failure_modes array (Stage1 schema)")
    print("  FM-CRIT-001: preserved as critical, evidence_ids=[]")
    print("  FM-HIGH-002: preserved as high, evidence_ids=['EVID-001']")

    # Save pre-resolve state for version tracking
    version_before = int(ctx.stage_output_versions.get("stage_1", 1))

    try:
        resolved = resolve_action(
            ctx,
            action_id=edit_action.action_id,
            decision="edit",
            note="已补充证据引用，添加 EVID-001 到 FM-HIGH-002",
            payload_after=valid_payload,
        )
        print(
            f"[probe] LEGAL resolve SUCCESS: status={resolved.status} decision={resolved.reviewer_decision}"
        )
    except (TransitionPolicyError, ValueError) as e:
        errors.append(f"Legal structured edit was rejected: {e}")
        print(f"[probe] LEGAL resolve REJECTED: {e}")
        resolved = None

    if resolved and resolved.status == "resolved":
        version_after = int(ctx.stage_output_versions.get("stage_1", 1))
        print(f"[probe] Stage output version: {version_before} → {version_after}")
        print(f"[probe] Stage output edited: {ctx.stage_1_output.failure_modes[-1].evidence_ids}")

    # ── 7. Save and reload from PostgreSQL ────────────────────────────────────
    session_store.save(ctx)
    print("[probe] Saved after legal structured edit")

    reloaded = session_store.load(session_id)
    if reloaded is None:
        errors.append("CRITICAL: reloaded context is None")
        sys.exit(1)

    print(f"[probe] Reloaded from PostgreSQL: state={reloaded.current_state.value}")

    # Find the edit action in reloaded context
    reloaded_edit = next(
        (a for a in reloaded.pending_actions if a.action_id == edit_action.action_id),
        None,
    )
    if reloaded_edit is None:
        print(
            "[probe] WARNING: Edit action not found in reloaded context (may have been superseded after version bump)"
        )
        # Check for superseded status via table
        ha_rows_target = query_table(
            "SELECT action_id, status, reviewer_decision, payload_after IS NOT NULL AS has_payload "
            "FROM human_actions WHERE session_id = %s AND action_id = %s",
            (session_id, edit_action.action_id),
        )
        resolved_status = ha_rows_target[0]["status"] if ha_rows_target else "NOT_FOUND"
        has_payload_after = bool(ha_rows_target[0]["has_payload"]) if ha_rows_target else False
    else:
        resolved_status = reloaded_edit.status
        has_payload_after = reloaded_edit.payload_after is not None

    print(f"[probe] Edit action in reloaded context: {resolved_status}")

    # ── 8. Query independent tables ───────────────────────────────────────────
    ha_rows = query_table(
        "SELECT action_id, action_type, status, reviewer_decision, "
        "payload_after IS NOT NULL AS has_payload_after, stage_output_version "
        "FROM human_actions WHERE session_id = %s AND action_id = %s",
        (session_id, edit_action.action_id),
    )
    ha_status = ha_rows[0]["status"] if ha_rows else "NOT_FOUND"
    ha_payload = bool(ha_rows[0]["has_payload_after"]) if ha_rows else False
    print(f"[probe] human_actions table: status={ha_status}, has_payload_after={ha_payload}")

    ae_rows = query_table(
        "SELECT event_id, event_type, target_id "
        "FROM audit_events WHERE session_id = %s AND event_type = 'human_action_resolved' AND target_id = %s",
        (session_id, edit_action.action_id),
    )
    has_resolution_event = len(ae_rows) > 0
    print(f"[probe] audit_events table: human_action_resolved for edit = {len(ae_rows)}")
    for ae in ae_rows:
        print(f"  {ae['event_id']} {ae['event_type']} target={ae['target_id']}")

    # ── 9. Stage Gate after legal edit (on reloaded context) ──────────────────
    gate_after = evaluate_stage_gate(reloaded, 1)
    print(
        f"\n[probe] Stage Gate AFTER legal edit: can_continue={gate_after.can_continue}, blockers={len(gate_after.blockers)}"
    )
    for b in gate_after.blockers:
        print(f"  [{b.blocker_type}] {b.message[:140]}")

    final_state = str(reloaded.current_state.value)
    remaining_pending = reloaded.get_pending_actions(stage=1)

    print(f"\n[probe] Final state: {final_state}")
    print(f"[probe] Remaining pending actions: {len(remaining_pending)}")
    for a in remaining_pending:
        print(
            f"  {a.action_id} type={a.action_type} source={a.source_type}/{a.source_id} status={a.status} v={a.stage_output_version}"
        )

    # ── 10. Verify other actions not batch-cleared ────────────────────────────
    # After version bump, superseded actions should exist (not deleted)
    superseded_count = sum(
        1 for a in reloaded.pending_actions if a.status == HumanActionStatus.SUPERSEDED.value
    )
    print(f"[probe] Superseded actions: {superseded_count}")
    total_actions = len(reloaded.pending_actions)
    print(
        f"[probe] Total actions in context: {total_actions} (including resolved + superseded + pending)"
    )

    # ── 11. Build JSON report ─────────────────────────────────────────────────
    has_langgraph_interrupt = os.environ.get("WORKFLOW_EXECUTION_MODE") == "langgraph_interrupt"

    report = {
        "session_id": session_id,
        "postgres_available": pg_available,
        "initial_state": "s1_review",
        "edit_action": {
            "action_id": edit_action.action_id,
            "status": "pending",
            "source_type": edit_action.source_type,
            "blocking": edit_action.blocking,
            "requires_structured_output": requires_structured,
        },
        "stage_gate_before": {
            "allowed_to_advance": gate_before.can_continue,
            "blockers_count": len(gate_before.blockers),
            "blocker_types": sorted({b.blocker_type for b in gate_before.blockers}),
        },
        "invalid_without_payload": {
            "attempted": True,
            "rejected_by_policy": illegal_no_payload_rejected,
            "action_status_after": status_after_no_payload,
        },
        "invalid_incomplete_payload": {
            "attempted": True,
            "rejected_by_policy": illegal_incomplete_rejected,
            "action_status_after": status_after_incomplete,
        },
        "valid_structured_edit": {
            "attempted": True,
            "action_status_after": ha_status,
            "payload_after_persisted": ha_payload,
            "audit_event_created": has_resolution_event,
        },
        "reloaded_from_postgres": reloaded is not None,
        "human_actions_table_status": ha_status,
        "human_actions_table_has_payload_after": ha_payload,
        "audit_events_table_has_resolution_event": has_resolution_event,
        "stage_gate_after": {
            "allowed_to_advance": gate_after.can_continue,
            "remaining_blockers_count": len(gate_after.blockers),
            "blocker_types": sorted({b.blocker_type for b in gate_after.blockers}),
        },
        "final_state": final_state,
        "advanced_to_stage_2": final_state != "s1_review",
        "used_langgraph_interrupt": has_langgraph_interrupt,
    }

    print("\n" + "=" * 60)
    print("AC-05B-2 PROBE RESULT (JSON):")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # ── 12. Acceptance assertions ─────────────────────────────────────────────
    if not evidence_gap_edits:
        errors.append("FAIL: No evidence_gap edit action exists")
    if not requires_structured:
        errors.append("FAIL: evidence_gap edit action does not require structured output")
    if gate_before.can_continue:
        errors.append("FAIL: Gate allowed advancement before resolution")
    if not illegal_no_payload_rejected:
        errors.append("FAIL: Edit without payload_after was not rejected")
    if status_after_no_payload != "pending":
        errors.append(
            f"FAIL: Action status changed to '{status_after_no_payload}' after no-payload attempt"
        )
    if not illegal_incomplete_rejected:
        errors.append("FAIL: Edit with incomplete payload was not rejected")
    if status_after_incomplete != "pending":
        errors.append(
            f"FAIL: Action status changed to '{status_after_incomplete}' after incomplete-payload attempt"
        )
    if has_fake_resolution:
        errors.append("FAIL: Fake human_action_resolved found after illegal attempts")
    if ha_status != "resolved":
        errors.append(f"FAIL: human_actions table status is '{ha_status}', expected 'resolved'")
    if not ha_payload:
        errors.append("FAIL: payload_after not persisted in human_actions table")
    if not has_resolution_event:
        errors.append("FAIL: No human_action_resolved audit event found")
    if gate_after.can_continue:
        errors.append("FAIL: Gate allowed advancement after resolving only one edit action")
    if final_state != "s1_review":
        errors.append(f"FAIL: Final state is '{final_state}', expected 's1_review'")

    if errors:
        print("\n*** ACCEPTANCE FAILURES ***")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n*** ACCEPTANCE PASSED: All AC-05B-2 criteria satisfied ***")


if __name__ == "__main__":
    main()
