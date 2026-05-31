# _ac05c_r_formal_advance_probe.py -- AC-05C-R formal single_step advance path probe.
# Tests: session with cleared gate → run_one_step("确认") → s2_running WITHOUT Stage 2 LLM.
# Key constraint: NO manual current_state assignment. Must use run_one_step formal path.
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

    # ── 1. Build s1_review session and clear ALL blockers ──────────────────
    ctx = ProjectContext()
    ctx.research_target = "GPT-4o"
    ctx.domain = "法律文书生成"
    ctx.goal = "提高合同起草准确率"
    ctx.current_state = SessionState.S1_REVIEW

    evidence = EvidenceSource(
        evidence_id="EVID-LEGAL-001",
        session_id=ctx.session_id,
        title="民法典 第496条 格式条款",
        url="https://example.com/civil-code-496",
        source_type="official_doc",
        credibility_score=0.85,
        summary="《中华人民共和国民法典》第496条",
        claims=["格式条款提供方应当遵循公平原则"],
        verified=False,
    )
    ctx.evidence_sources.append(evidence)

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
        direct_conclusion="GPT-4o 存在 critical 级别的自主决策风险。",
        search_sources=[],
        raw_summary="完整原始输出...",
    )
    ctx.stage_output_versions["stage_1"] = 1

    from core.evidence_service import link_failure_modes_to_evidence

    link_failure_modes_to_evidence(ctx)

    # Create review actions
    from core.oversight_service import create_review_actions_for_stage

    created = create_review_actions_for_stage(ctx, 1)
    print(f"[probe] Created {len(created)} PendingHumanAction(s)")

    all_actions = ctx.get_pending_actions(stage=1)
    print(f"[probe] Actions ({len(all_actions)}):")
    for a in all_actions:
        print(
            f"  {a.action_id} type={a.action_type} source={a.source_type}/{a.source_id} status={a.status} blocking={a.blocking}"
        )

    # Check initial gate
    from core.stage_readiness_service import evaluate_stage_gate

    gate_initial = evaluate_stage_gate(ctx, 1)
    print(
        f"\n[probe] Initial gate: can_continue={gate_initial.can_continue}, blockers={len(gate_initial.blockers)}"
    )
    for b in gate_initial.blockers:
        print(f"  [{b.blocker_type}] {b.message[:120]}")

    # ── 2. Resolve ALL blockers via formal resolve_action ──────────────────
    from core.evidence_service import verify_evidence_source
    from core.oversight_service import resolve_action, resolve_actions_for_evidence

    # Resolve escalate action
    escalate_actions = [a for a in all_actions if str(a.action_type) == "escalate"]
    if escalate_actions:
        resolved = resolve_action(
            ctx,
            action_id=escalate_actions[0].action_id,
            decision="approve",
            note="负责人已审查 critical 风险，批准继续。",
        )
        print(f"[probe] Resolved escalate: {resolved.status}")

    # Resolve evidence_gap edit with valid payload
    edit_actions = [
        a
        for a in ctx.get_pending_actions(stage=1)
        if str(a.action_type) == "edit" and a.status == "pending"
    ]
    if edit_actions:
        valid_payload = {
            "failure_modes": [
                {
                    "id": "FM-CRIT-001",
                    "category": "模型自主决策超出边界",
                    "description": "模型在无人工确认的情况下自动生成了具有法律约束力的条款建议",
                    "severity": "critical",
                    "evidence_ids": ["EVID-LEGAL-001"],
                    "evidence": "测试中模型直接输出完整合同模板，补充证据引用。",
                }
            ],
            "direct_conclusion": "GPT-4o 存在 critical 级别的自主决策风险，已补充证据引用。",
        }
        resolved = resolve_action(
            ctx,
            action_id=edit_actions[0].action_id,
            decision="edit",
            note="已补充 evidence_ids 引用 EVID-LEGAL-001。",
            payload_after=valid_payload,
        )
        print(f"[probe] Resolved edit: {resolved.status} (version bump may have occurred)")

    # After version bump from edit, resolve any new v2 actions
    all_pending_after_edit = ctx.get_pending_actions(stage=1)
    for a in all_pending_after_edit:
        if a.status != "pending":
            continue
        if str(a.action_type) == "escalate":
            resolved = resolve_action(
                ctx, action_id=a.action_id, decision="approve", note="v2 批准 critical 升级风险。"
            )
            print(f"[probe] Resolved escalate v2: {a.action_id} -> {resolved.status}")
        elif str(a.action_type) == "approve":
            resolved = resolve_action(
                ctx, action_id=a.action_id, decision="approve", note="v2 批准高风险项。"
            )
            print(f"[probe] Resolved approve v2: {a.action_id} -> {resolved.status}")
        elif str(a.action_type) == "verify_evidence":
            # Verify evidence first, then cascade
            verify_evidence_source(
                ctx, evidence_id="EVID-LEGAL-001", note="人工核验：民法典第496条内容属实。"
            )
            resolved_ids = resolve_actions_for_evidence(
                ctx, evidence_id="EVID-LEGAL-001", decision="verify_evidence", note="证据核验完成。"
            )
            print(f"[probe] Evidence verified + cascade: {len(resolved_ids)} actions")

    # Save pre-advance state
    session_store.save(ctx)
    session_id = ctx.session_id
    print(f"\n[probe] Saved session {session_id} to PostgreSQL")

    # ── 3. Verify gate is CLEAR before advance ───────────────────────────────
    gate_before = evaluate_stage_gate(ctx, 1)
    print(
        f"\n[probe] Gate BEFORE advance: can_continue={gate_before.can_continue}, blockers={len(gate_before.blockers)}"
    )
    for b in gate_before.blockers:
        print(f"  [{b.blocker_type}] {b.message[:120]}")

    before_state = str(ctx.current_state.value)
    print(f"[probe] Current state before advance: {before_state}")

    all_stage1_actions = [a for a in ctx.pending_actions if a.stage_id == 1]
    pending_blocking = [a for a in all_stage1_actions if a.status == "pending" and a.blocking]
    print(f"[probe] Pending blocking actions: {len(pending_blocking)}")
    for a in pending_blocking:
        print(f"  {a.action_id} type={a.action_type} v={a.stage_output_version}")

    if not gate_before.can_continue:
        errors.append("FAIL: Gate not clear before advance attempt")
        print("\n*** BLOCKING: Gate does not allow advance ***")
        sys.exit(1)
    if len(gate_before.blockers) > 0:
        errors.append(f"FAIL: {len(gate_before.blockers)} blockers remain")
        print("\n*** BLOCKING: Blockers still exist ***")
        sys.exit(1)

    # ── 4. Advance via FORMAL run_one_step path ──────────────────────────────
    print(f"\n{'=' * 60}")
    print("[ADVANCE] Calling run_one_step() with user_input='确认'")
    print("=" * 60)

    # Set pending_input so run_one_step picks it up
    ctx.pending_input = "确认"

    from graph.runner import run_one_step

    manual_state_assignment_used = False
    formal_path = "run_one_step -> node_s1_review -> node_stage_review(approve)"

    try:
        ctx = run_one_step(ctx)
        after_state = str(ctx.current_state.value)
        print(f"[probe] run_one_step returned: state={after_state}")
    except Exception as e:
        errors.append(f"run_one_step failed: {e}")
        print(f"[probe] run_one_step ERROR: {e}")
        after_state = str(ctx.current_state.value)

    # ── 5. Verify post-advance state ─────────────────────────────────────────
    stage_2_output_exists = ctx.stage_2_output is not None
    print(f"[probe] stage_2_output exists: {stage_2_output_exists}")

    entered_s2_review = after_state == "s2_review"
    entered_complete = after_state == "complete"
    advanced_to_s2_running = after_state == "s2_running"

    print(f"[probe] After advance: state={after_state}")
    print(f"[probe] advanced_to_s2_running={advanced_to_s2_running}")
    print(f"[probe] entered_s2_review={entered_s2_review}")
    print(f"[probe] entered_complete={entered_complete}")

    # ── 6. Save and reload from PostgreSQL ───────────────────────────────────
    session_store.save(ctx)
    print("[probe] Saved after formal advance")

    reloaded = session_store.load(session_id)
    if reloaded is None:
        errors.append("CRITICAL: reloaded context is None")
        sys.exit(1)

    postgres_state_after = str(reloaded.current_state.value)
    print(f"[probe] Reloaded from PostgreSQL: state={postgres_state_after}")

    # Query independent tables
    ha_count = query_table(
        "SELECT COUNT(*) as cnt FROM human_actions WHERE session_id = %s",
        (session_id,),
    )[0]["cnt"]
    ae_count = query_table(
        "SELECT COUNT(*) as cnt FROM audit_events WHERE session_id = %s",
        (session_id,),
    )[0]["cnt"]
    print(f"[probe] human_actions table: {ha_count} rows")
    print(f"[probe] audit_events table: {ae_count} rows")

    # Verify no Stage 2 output in reloaded context
    reloaded_s2_output = reloaded.stage_2_output is not None
    print(f"[probe] Reloaded stage_2_output exists: {reloaded_s2_output}")

    # ── 7. Build JSON report ─────────────────────────────────────────────────
    has_langgraph_interrupt = os.environ.get("WORKFLOW_EXECUTION_MODE") == "langgraph_interrupt"

    report = {
        "session_id": session_id,
        "postgres_available": pg_available,
        "before_state": before_state,
        "gate_before_advance": {
            "allowed_to_advance": gate_before.can_continue,
            "blockers_count": len(gate_before.blockers),
            "blocker_types": sorted({b.blocker_type for b in gate_before.blockers}),
        },
        "used_formal_advance_path": True,
        "manual_state_assignment_used": manual_state_assignment_used,
        "formal_path": formal_path,
        "after_state": after_state,
        "stage_2_output_exists": stage_2_output_exists,
        "stage_2_llm_executed": stage_2_output_exists,
        "entered_s2_review": entered_s2_review,
        "entered_complete": entered_complete,
        "reloaded_from_postgres": reloaded is not None,
        "postgres_state_after": postgres_state_after,
        "used_langgraph_interrupt": has_langgraph_interrupt,
    }

    print("\n" + "=" * 60)
    print("AC-05C-R PROBE RESULT (JSON):")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # ── 8. Acceptance assertions ─────────────────────────────────────────────
    # C1: Before state is s1_review
    if before_state != "s1_review":
        errors.append(f"FAIL [C1]: Before state is '{before_state}', expected 's1_review'")

    # C2: Gate allowed_to_advance=true and blockers=0
    if not gate_before.can_continue:
        errors.append("FAIL [C2]: Gate can_continue is False")
    if gate_before.blockers:
        errors.append(f"FAIL [C2]: {len(gate_before.blockers)} blockers remain")

    # C3: Advanced through formal path (run_one_step)
    if not advanced_to_s2_running:
        errors.append(
            f"FAIL [C3]: Did not advance to s2_running through formal path. State is '{after_state}'"
        )

    # C4: No manual state assignment
    if manual_state_assignment_used:
        errors.append("FAIL [C4]: Manual current_state assignment was used")

    # C5: After state is s2_running
    if after_state != "s2_running":
        errors.append(f"FAIL [C5]: After state is '{after_state}', expected 's2_running'")

    # C6: No Stage 2 LLM executed
    if stage_2_output_exists:
        errors.append("FAIL [C6]: stage_2_output exists, Stage 2 LLM was executed")

    # C7: No stage_2_output generated
    if stage_2_output_exists:
        errors.append("FAIL [C7]: stage_2_output was generated")

    # C8: Not in s2_review or complete
    if entered_s2_review:
        errors.append("FAIL [C8]: Entered s2_review (should be s2_running)")
    if entered_complete:
        errors.append("FAIL [C8]: Entered complete state")

    # C9: PostgreSQL reload confirms s2_running
    if postgres_state_after != "s2_running":
        errors.append(
            f"FAIL [C9]: PostgreSQL state after is '{postgres_state_after}', expected 's2_running'"
        )

    # C10: No LangGraph interrupt
    # (verified by construction)

    if errors:
        print("\n*** ACCEPTANCE FAILURES ***")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n*** ACCEPTANCE PASSED: All AC-05C-R criteria satisfied ***")


if __name__ == "__main__":
    main()
