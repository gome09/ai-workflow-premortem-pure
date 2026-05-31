# _ac05a_probe.py -- AC-05A minimal closed-loop acceptance probe.
# Exercises the formal business logic layer without PostgreSQL, pytest,
# LangGraph interrupt, Tavily, or the full 4-stage flow.
from __future__ import annotations

import json
import os
import sys

# Enforce required configuration before any project imports.
os.environ.setdefault("DEEPSEEK_API_KEY", "test_deepseek_key")
os.environ.setdefault("TAVILY_API_KEY", "healthcheck_dummy")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pg_password")
os.environ["WORKFLOW_EXECUTION_MODE"] = "single_step"
os.environ["STAGE_OUTPUT_MODE"] = "json_first"

from core.models import (
    FailureMode,
    FlaggedItem,
    FlagStatus,
    ProjectContext,
    SessionState,
    Stage1Output,
)


def main() -> None:
    # ── 1. Build an s1_review session with governed content ──────────────────
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

    # ── 2. Create pending actions via the formal oversight service ────────────
    from core.oversight_service import create_review_actions_for_stage

    created = create_review_actions_for_stage(ctx, 1)
    print(f"[probe] Created {len(created)} PendingHumanAction(s) via formal oversight_service")

    initial_pending = ctx.get_pending_actions(stage=1)
    initial_action_types = sorted({str(a.action_type) for a in initial_pending})
    initial_pending_count = len(initial_pending)

    print(f"[probe] Initial pending actions: {initial_pending_count}")
    for a in initial_pending:
        print(
            f"  - {a.action_id} type={a.action_type} status={a.status} blocking={a.blocking} source={a.source_type}/{a.source_id}"
        )

    # ── 3. Stage Gate before any resolution ───────────────────────────────────
    from core.stage_readiness_service import evaluate_stage_gate

    gate_before = evaluate_stage_gate(ctx, 1)
    print(
        f"\n[probe] Stage Gate (before resolution): can_continue={gate_before.can_continue}, blockers={len(gate_before.blockers)}"
    )
    for b in gate_before.blockers:
        print(f"  - {b.blocker_type} | {b.message[:100]}")

    audit_before = len(ctx.audit_events)
    print(f"\n[probe] Audit events before resolution: {audit_before}")
    for ae in ctx.audit_events:
        print(f"  - {ae.event_id} {ae.event_type} target={ae.target_id}")

    # ── 4. Resolve exactly one action via formal resolve_action ──────────────
    from core.oversight_service import resolve_action

    verify_actions = [a for a in initial_pending if str(a.action_type) == "verify_evidence"]
    target_action = verify_actions[0] if verify_actions else initial_pending[0]

    print(f"\n[probe] Resolving action: {target_action.action_id} type={target_action.action_type}")

    resolved = resolve_action(
        ctx,
        action_id=target_action.action_id,
        decision="verify_evidence",
        note="人工核验通过：该引用已在官方文档中确认。",
    )
    print(
        f"[probe] Action {resolved.action_id} resolved: status={resolved.status} decision={resolved.reviewer_decision}"
    )

    # ── 5. Stage Gate after ONE resolution ────────────────────────────────────
    gate_after = evaluate_stage_gate(ctx, 1)
    audit_after = len(ctx.audit_events)
    print(
        f"\n[probe] Stage Gate (after one resolution): can_continue={gate_after.can_continue}, blockers={len(gate_after.blockers)}"
    )
    for b in gate_after.blockers:
        print(f"  - {b.blocker_type} | {b.message[:100]}")

    print(f"\n[probe] Audit events after resolution: {audit_after}")
    for ae in ctx.audit_events:
        print(f"  - {ae.event_id} {ae.event_type} target={ae.target_id}")

    # ── 6. Verify state integrity ─────────────────────────────────────────────
    final_state = str(ctx.current_state.value)
    remaining_pending = ctx.get_pending_actions(stage=1)
    remaining_blocking = [a for a in remaining_pending if a.blocking]

    print(f"\n[probe] Final state: {final_state}")
    print(f"[probe] Remaining pending actions: {len(remaining_pending)}")
    print(f"[probe] Remaining blocking actions: {len(remaining_blocking)}")
    for a in remaining_pending:
        print(f"  - {a.action_id} type={a.action_type} status={a.status} blocking={a.blocking}")

    # ── 7. Build the JSON report ──────────────────────────────────────────────
    has_langgraph_interrupt = os.environ.get("WORKFLOW_EXECUTION_MODE") == "langgraph_interrupt"

    report = {
        "session_id": ctx.session_id,
        "initial_state": "s1_review",
        "initial_pending_actions_count": initial_pending_count,
        "initial_action_types": initial_action_types,
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
    print("AC-05A PROBE RESULT (JSON):")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # ── 8. Assertions ─────────────────────────────────────────────────────────
    errors: list[str] = []

    if initial_pending_count == 0:
        errors.append("FAIL: No pending actions were created")
    if gate_before.can_continue:
        errors.append("FAIL: Stage Gate allowed advancement before any action resolution")
    if not gate_before.blockers:
        errors.append("FAIL: Stage Gate reported zero blockers before resolution")
    if resolved.status != "resolved":
        errors.append(f"FAIL: Resolved action status is '{resolved.status}', expected 'resolved'")
    if audit_after <= audit_before:
        errors.append("FAIL: Audit events did not increase after action resolution")
    if gate_after.can_continue:
        errors.append(
            "FAIL: Stage Gate allowed advancement after resolving only one action (other blockers remain)"
        )
    if final_state != "s1_review":
        errors.append(f"FAIL: Final state is '{final_state}', expected 's1_review'")

    if errors:
        print("\n*** ACCEPTANCE FAILURES ***")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n*** ACCEPTANCE PASSED: All AC-05A criteria satisfied ***")


if __name__ == "__main__":
    main()
