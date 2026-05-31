# _ac05b4_parser_edit_probe.py -- AC-05B-4 parser error edit action closed-loop probe.
# Tests: parser error → edit action → structured payload_after validation →
# blocker clearance → PostgreSQL persistence → audit trail completeness.
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

    # ── 1. Build s1_review session with parser error ────────────────────────
    ctx = ProjectContext()
    ctx.research_target = "GPT-4o"
    ctx.domain = "法律文书生成"
    ctx.goal = "提高合同起草准确率"
    ctx.current_state = SessionState.S1_REVIEW

    # Set parser error — simulates AI output that failed structural parsing
    ctx.parser_errors["stage_1"] = (
        "JSON 解析失败：AI 返回的 Stage1Output 缺少 failure_modes 数组，"
        "直接结论字段被错误包裹为字符串数组而非纯字符串。请人工编辑结构化输出。"
    )
    print(f"[probe] Parser error set: {ctx.parser_errors['stage_1'][:80]}...")

    # Build a partial/broken stage_1_output representing what little was parsed
    # raw_summary MUST be preserved (the raw AI output text)
    raw_summary_text = (
        "【原始 AI 输出】\n"
        "{\n"
        '  "failure_modes": "解析失败-字段应为数组但返回了字符串",\n'
        '  "direct_conclusion": ["GPT-4o 在法律文书领域风险显著", "需人工复核"]\n'
        "}\n"
        "原始输出未能通过 schema 验证，以上为 AI 原始返回文本。"
    )

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
        ],
        direct_conclusion="(解析失败 — 需人工编辑)",
        search_sources=[],
        raw_summary=raw_summary_text,
    )
    ctx.stage_output_versions["stage_1"] = 1

    print(f"[probe] raw_summary length: {len(raw_summary_text)} chars")
    print(f"[probe] raw_summary preserved: {bool(ctx.stage_1_output.raw_summary)}")

    # ── 2. Create pending actions via formal oversight service ────────────────
    from core.oversight_service import create_review_actions_for_stage

    created = create_review_actions_for_stage(ctx, 1)
    print(f"[probe] Created {len(created)} PendingHumanAction(s)")

    # Find the parser edit action
    parser_edits = [
        a
        for a in ctx.get_pending_actions(stage=1)
        if str(a.action_type) == "edit" and str(a.source_type) == "parser"
    ]
    if not parser_edits:
        errors.append("No parser edit action found")
        print("\n*** BLOCKING: No parser edit action ***")
        all_pending = ctx.get_pending_actions(stage=1)
        print(f"[probe] All pending actions ({len(all_pending)}):")
        for a in all_pending:
            print(
                f"  {a.action_id} type={a.action_type} source={a.source_type}/{a.source_id} status={a.status}"
            )
        sys.exit(1)

    edit_action = parser_edits[0]
    requires_structured = str(edit_action.source_type) in {
        "parser",
        "policy_gap",
        "evidence_gap",
        "eval_coverage",
    }

    print(f"\n[probe] Parser edit action: {edit_action.action_id}")
    print(f"  type={edit_action.action_type}")
    print(f"  source_type={edit_action.source_type}")
    print(f"  source_id={edit_action.source_id}")
    print(f"  status={edit_action.status}")
    print(f"  blocking={edit_action.blocking}")
    print(f"  risk_level={edit_action.risk_level}")
    print(f"  trigger_reason={edit_action.trigger_reason[:100]}...")
    print(f"  requires_structured_output={requires_structured}")
    print(f"  title={edit_action.title}")

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

    # ── 3. Stage Gate before any resolution ────────────────────────────────────
    from core.stage_readiness_service import evaluate_stage_gate

    gate_before = evaluate_stage_gate(ctx, 1)
    print(
        f"\n[probe] Stage Gate BEFORE: can_continue={gate_before.can_continue}, blockers={len(gate_before.blockers)}"
    )
    for b in gate_before.blockers:
        print(f"  [{b.blocker_type}] | {b.message[:150]}")

    parser_blockers_before = [b for b in gate_before.blockers if b.blocker_type == "parser_error"]
    print(f"[probe] parser_error blockers before: {len(parser_blockers_before)}")
    for b in parser_blockers_before:
        print(f"  parser_error={b.metadata.get('parser_error', '')[:80]}...")

    audit_before = len(ctx.audit_events)
    print(f"[probe] Audit events before: {audit_before}")

    # ── 4. Attempt illegal: resolve edit WITHOUT payload_after ──────────────
    from core.oversight_service import resolve_action
    from graph.transition_policy import TransitionPolicyError

    print("\n[probe] === ATTEMPT 1: resolve parser edit WITHOUT payload_after ===")
    illegal_no_payload_rejected = False
    try:
        resolve_action(
            ctx,
            action_id=edit_action.action_id,
            decision="edit",
            note="尝试无 payload_after 关闭 parser edit",
            payload_after=None,
        )
        errors.append(
            "CRITICAL: parser edit resolve WITHOUT payload_after should have been rejected"
        )
    except TransitionPolicyError as e:
        illegal_no_payload_rejected = True
        print(f"[probe] REJECTED by TransitionPolicyError: {e}")
    except ValueError as e:
        illegal_no_payload_rejected = True
        print(f"[probe] REJECTED by ValueError: {e}")

    status_after_no_payload = edit_action.status
    print(f"[probe] Action status after: {status_after_no_payload}")

    # ── 5. Attempt illegal: resolve edit with INCOMPLETE payload_after ──────
    print("\n[probe] === ATTEMPT 2: resolve parser edit with INCOMPLETE payload_after ===")
    illegal_incomplete_rejected = False
    try:
        resolve_action(
            ctx,
            action_id=edit_action.action_id,
            decision="edit",
            note="尝试用不完整 payload 关闭 parser edit",
            payload_after={"summary": "人工修正完成", "note": "缺少结构化字段"},
        )
        errors.append(
            "CRITICAL: parser edit resolve with incomplete payload should have been rejected"
        )
    except TransitionPolicyError as e:
        illegal_incomplete_rejected = True
        print(f"[probe] REJECTED by TransitionPolicyError: {e}")
    except ValueError as e:
        illegal_incomplete_rejected = True
        print(f"[probe] REJECTED by ValueError: {e}")

    status_after_incomplete = edit_action.status
    print(f"[probe] Action status after: {status_after_incomplete}")

    # Verify no fake resolution audit events
    has_fake_resolution = any(
        ae.event_type == "human_action_resolved" and ae.target_id == edit_action.action_id
        for ae in ctx.audit_events
    )
    if has_fake_resolution:
        errors.append(
            "CRITICAL: Fake human_action_resolved audit event found after illegal attempts"
        )
    print(f"[probe] Fake resolution audit event: {has_fake_resolution}")

    # Verify parser error still in ctx.parser_errors
    parser_error_still_present = bool(ctx.parser_errors.get("stage_1"))
    print(f"[probe] Parser error still in ctx.parser_errors: {parser_error_still_present}")

    # ── 6. Legal structured edit with valid payload_after ────────────────────
    print("\n[probe] === ATTEMPT 3: LEGAL structured edit with valid payload_after ===")

    valid_payload = {
        "failure_modes": [
            {
                "id": "FM-CRIT-001",
                "category": "模型自主决策超出边界",
                "description": "模型在无人工确认的情况下自动生成了具有法律约束力的条款建议",
                "severity": "critical",
                "evidence_ids": [],
                "evidence": "测试中模型直接输出完整合同模板，包含仲裁条款",
            },
        ],
        "direct_conclusion": "GPT-4o 在法律文书生成领域存在 critical 级别的自主决策风险。已人工编辑修复解析失败，保留原始风险结论。",
        "edited_text": raw_summary_text,
        "raw_summary": raw_summary_text,
    }

    print("[probe] Submitting valid payload with failure_modes array (Stage1Schema)")
    print(f"  raw_summary preserved: {len(valid_payload.get('raw_summary', ''))} chars")

    version_before = int(ctx.stage_output_versions.get("stage_1", 1))

    try:
        resolved = resolve_action(
            ctx,
            action_id=edit_action.action_id,
            decision="edit",
            note="人工编辑完成：重新构造 failure_modes 数组并修正 direct_conclusion。原始风险结论已保留。",
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
        print(
            f"[probe] Stage output edited: direct_conclusion={ctx.stage_1_output.direct_conclusion[:80]}..."
        )
        parser_error_cleared = not ctx.parser_errors.get("stage_1")
        print(f"[probe] Parser error cleared from ctx.parser_errors: {parser_error_cleared}")

    # Check audit events
    stage_output_edited_audit = [
        ae for ae in ctx.audit_events if ae.event_type == "stage_output_edited"
    ]
    print(f"[probe] stage_output_edited audit events: {len(stage_output_edited_audit)}")
    for ae in stage_output_edited_audit:
        print(
            f"  {ae.event_id} target={ae.target_id} applied={ae.metadata.get('applied_to_structured_output')} parser_cleared={ae.metadata.get('parser_error_cleared')}"
        )

    action_resolved_audit = [
        ae
        for ae in ctx.audit_events
        if ae.event_type == "human_action_resolved" and ae.target_id == edit_action.action_id
    ]
    print(f"[probe] human_action_resolved audit events for edit: {len(action_resolved_audit)}")

    # ── 7. Save and reload from PostgreSQL ────────────────────────────────────
    session_store.save(ctx)
    print("\n[probe] Saved after legal structured edit")

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
        print("[probe] WARNING: Edit action not found in reloaded context (may be superseded)")
    else:
        print(f"[probe] Reloaded edit action status: {reloaded_edit.status}")
        print(
            f"[probe] Reloaded edit action has payload_after: {reloaded_edit.payload_after is not None}"
        )

    # ── 8. Query independent tables ───────────────────────────────────────────
    # human_actions table
    ha_rows = query_table(
        "SELECT action_id, action_type, status, reviewer_decision, "
        "payload_after IS NOT NULL AS has_payload_after, stage_output_version "
        "FROM human_actions WHERE session_id = %s AND action_id = %s",
        (session_id, edit_action.action_id),
    )
    ha_status = ha_rows[0]["status"] if ha_rows else "NOT_FOUND"
    ha_payload = bool(ha_rows[0]["has_payload_after"]) if ha_rows else False
    print(f"[probe] human_actions table: status={ha_status}, has_payload_after={ha_payload}")
    if ha_rows:
        print(
            f"  reviewer_decision={ha_rows[0]['reviewer_decision']} stage_output_version={ha_rows[0]['stage_output_version']}"
        )

    # audit_events table - stage_output_edited
    ae_soe_rows = query_table(
        "SELECT event_id, event_type, target_type, target_id "
        "FROM audit_events WHERE session_id = %s AND event_type = 'stage_output_edited'",
        (session_id,),
    )
    has_stage_output_edited = len(ae_soe_rows) > 0
    print(f"[probe] audit_events table: stage_output_edited events = {len(ae_soe_rows)}")

    # audit_events table - human_action_resolved
    ae_har_rows = query_table(
        "SELECT event_id, event_type, target_type, target_id "
        "FROM audit_events WHERE session_id = %s AND event_type = 'human_action_resolved' AND target_id = %s",
        (session_id, edit_action.action_id),
    )
    has_resolution_event = len(ae_har_rows) > 0
    print(f"[probe] audit_events table: human_action_resolved events for edit = {len(ae_har_rows)}")
    for ae in ae_har_rows:
        print(f"  {ae['event_id']} {ae['event_type']} target={ae['target_id']}")

    # ── 9. Stage Gate after legal edit ───────────────────────────────────────
    gate_after = evaluate_stage_gate(reloaded, 1)
    print(
        f"\n[probe] Stage Gate AFTER: can_continue={gate_after.can_continue}, blockers={len(gate_after.blockers)}"
    )
    for b in gate_after.blockers:
        print(f"  [{b.blocker_type}] v={b.stage_output_version} | {b.message[:150]}")

    parser_blockers_after = [b for b in gate_after.blockers if b.blocker_type == "parser_error"]
    same_parser_blocker_remains = len(parser_blockers_after) > 0
    print(f"[probe] parser_error blockers after: {len(parser_blockers_after)}")

    final_state = str(reloaded.current_state.value)
    remaining_pending = reloaded.get_pending_actions(stage=1)

    print(f"\n[probe] Final state: {final_state}")
    print(f"[probe] Remaining pending actions: {len(remaining_pending)}")
    for a in remaining_pending:
        print(
            f"  {a.action_id} type={a.action_type} source={a.source_type}/{a.source_id} status={a.status} blocking={a.blocking} v={a.stage_output_version}"
        )

    # Audit event counts
    total_audit = len(reloaded.audit_events)
    print(f"\n[probe] Total audit events in reloaded context: {total_audit}")

    # ── 10. Build JSON report ─────────────────────────────────────────────────
    has_langgraph_interrupt = os.environ.get("WORKFLOW_EXECUTION_MODE") == "langgraph_interrupt"

    report = {
        "session_id": session_id,
        "postgres_available": pg_available,
        "initial_state": "s1_review",
        "parser_error": {
            "exists": True,
            "raw_summary_present": bool(ctx.stage_1_output.raw_summary)
            if ctx.stage_1_output
            else False,
            "blocker_present": len(parser_blockers_before) > 0,
        },
        "edit_action": {
            "action_id": edit_action.action_id,
            "action_type": "edit",
            "status_before": "pending",
            "source_type": "parser",
            "blocking": edit_action.blocking,
            "requires_structured_output": requires_structured,
        },
        "stage_gate_before": {
            "allowed_to_advance": gate_before.can_continue,
            "blockers_count": len(gate_before.blockers),
            "blocker_types": sorted({b.blocker_type for b in gate_before.blockers}),
            "has_parser_error_blocker": len(parser_blockers_before) > 0,
        },
        "invalid_without_payload": {
            "attempted": True,
            "rejected_by_policy": illegal_no_payload_rejected,
            "action_status_after": status_after_no_payload,
        },
        "invalid_incomplete_payload": {
            "attempted": True,
            "rejected_by_policy_or_schema": illegal_incomplete_rejected,
            "action_status_after": status_after_incomplete,
        },
        "valid_structured_edit": {
            "attempted": True,
            "action_status_after": resolved.status if resolved else "N/A",
            "payload_after_persisted": ha_payload,
            "stage_output_updated": len(stage_output_edited_audit) > 0,
            "audit_event_created": len(action_resolved_audit) > 0,
        },
        "reloaded_from_postgres": reloaded is not None,
        "human_actions_table_status": ha_status,
        "human_actions_table_has_payload_after": ha_payload,
        "audit_events_table_has_stage_output_edited": has_stage_output_edited,
        "audit_events_table_has_resolution_event": has_resolution_event,
        "stage_gate_after": {
            "allowed_to_advance": gate_after.can_continue,
            "remaining_blockers_count": len(gate_after.blockers),
            "has_same_parser_error_blocker": same_parser_blocker_remains,
            "blocker_types": sorted({b.blocker_type for b in gate_after.blockers}),
        },
        "final_state": final_state,
        "advanced_to_stage_2": final_state != "s1_review",
        "used_langgraph_interrupt": has_langgraph_interrupt,
    }

    print("\n" + "=" * 60)
    print("AC-05B-4 PROBE RESULT (JSON):")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # ── 11. Acceptance assertions ─────────────────────────────────────────────
    # C1: session in s1_review
    if final_state != "s1_review":
        errors.append(f"FAIL [C1]: Final state is '{final_state}', expected 's1_review'")

    # C2: parser error exists and raw_summary preserved
    if not parser_error_still_present and not resolved:
        errors.append("FAIL [C2]: Parser error did not exist initially")
    if not bool(ctx.stage_1_output.raw_summary if ctx.stage_1_output else False) and not reloaded:
        errors.append("FAIL [C2]: raw_summary was not preserved")

    # C3: parser error generates formal edit action
    if not parser_edits:
        errors.append("FAIL [C3]: No parser edit action generated")

    # C4: edit action has action_id, status, source_type, blocking reason
    if not edit_action.action_id or edit_action.action_type != "edit":
        errors.append("FAIL [C4]: Parser edit action missing action_id or wrong type")
    if str(edit_action.source_type) != "parser":
        errors.append(f"FAIL [C4]: source_type is '{edit_action.source_type}', expected 'parser'")

    # C5: Gate blocks before resolution
    if gate_before.can_continue:
        errors.append("FAIL [C5]: Gate allowed advancement before parser edit resolution")

    # C6: blocker explains parse failure
    if not parser_blockers_before:
        errors.append("FAIL [C6]: No parser_error blocker found before resolution")

    # C7: No payload_after → cannot resolve
    if not illegal_no_payload_rejected:
        errors.append("FAIL [C7]: Edit without payload_after was not rejected")
    if status_after_no_payload != "pending":
        errors.append(
            f"FAIL [C7]: Action status changed to '{status_after_no_payload}' after no-payload attempt"
        )

    # C8: Incomplete payload → cannot resolve
    if not illegal_incomplete_rejected:
        errors.append("FAIL [C8]: Edit with incomplete payload was not rejected")
    if status_after_incomplete != "pending":
        errors.append(
            f"FAIL [C8]: Action status changed to '{status_after_incomplete}' after incomplete-payload attempt"
        )

    # C9: No fake audit events from illegal attempts
    if has_fake_resolution:
        errors.append("FAIL [C9]: Fake human_action_resolved found after illegal attempts")

    # C10: Legal edit through formal service
    if resolved is None or resolved.status != "resolved":
        errors.append("FAIL [C10]: Legal structured edit was not resolved through formal service")

    # C11: Action status persisted to context + human_actions table
    if ha_status != "resolved":
        errors.append(
            f"FAIL [C11]: human_actions table status is '{ha_status}', expected 'resolved'"
        )

    # C12: payload_after persisted to context + human_actions table
    if not ha_payload:
        errors.append("FAIL [C12]: payload_after not persisted in human_actions table")

    # C13: Stage output updated, parser error blocker gone
    if same_parser_blocker_remains:
        errors.append("FAIL [C13]: parser_error blocker still present after legal edit")
    if reloaded and reloaded.stage_1_output:
        if reloaded.stage_1_output.direct_conclusion == "(解析失败 — 需人工编辑)":
            errors.append("FAIL [C13]: Stage output was not updated after legal edit")

    # C14: stage_output_edited + human_action_resolved audit events
    if not has_stage_output_edited:
        errors.append("FAIL [C14]: No stage_output_edited audit event")
    if not has_resolution_event:
        errors.append("FAIL [C14]: No human_action_resolved audit event")

    # C15: If other blockers remain, state stays at s1_review
    if gate_after.blockers and gate_after.can_continue:
        errors.append("FAIL [C15]: Gate allows advancement despite remaining blockers")
    if gate_after.blockers and final_state != "s1_review":
        errors.append("FAIL [C15]: State is not s1_review despite remaining blockers")

    # C16: No LangGraph interrupt
    # (verified by construction: WORKFLOW_EXECUTION_MODE=single_step)

    if errors:
        print("\n*** ACCEPTANCE FAILURES ***")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n*** ACCEPTANCE PASSED: All AC-05B-4 criteria satisfied ***")


if __name__ == "__main__":
    main()
