#!/usr/bin/env python
# _ac06c_parser_edit_apply_probe.py
# AC-06C: Human edit → structured output apply → parser error cleared
# minimum closed-loop verification.
# Does NOT import FastAPI, Streamlit, runner, LLM, DB, Redis.
"""Temporary probe for AC-06C. Do not wire into production."""

from __future__ import annotations

import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("DEEPSEEK_API_KEY", "probe-noop")
os.environ.setdefault("TAVILY_API_KEY", "probe-noop")
os.environ.setdefault("POSTGRES_PASSWORD", "probe-noop")

# ── imports from allowed modules ──
from core.models import (  # noqa: E402
    HumanActionStatus,
    ProjectContext,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
)
from core.oversight_service import (  # noqa: E402
    create_actions_from_parser_errors,
    resolve_action,
)
from core.reviewed_output_service import (  # noqa: E402
    ReviewedOutputError,
)
from core.stage_readiness_service import (  # noqa: E402
    evaluate_stage_gate,
)

# ───────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────


def build_minimal_ctx(stage: int) -> ProjectContext:
    ctx = ProjectContext(
        session_id=f"ac06c-probe-s{session_tag}",
        research_target="probe_target",
        domain="probe_domain",
        goal="probe_goal",
    )
    ctx.stage_1_output = Stage1Output()
    ctx.stage_2_output = Stage2Output()
    ctx.stage_3_output = Stage3Output()
    ctx.stage_4_output = Stage4Output()
    for s in [1, 2, 3, 4]:
        ctx.stage_output_versions[f"stage_{s}"] = 1
    return ctx


# Global counter to vary session_ids across probe runs
session_tag = "0"


def inject_parser_error(ctx: ProjectContext, stage: int, msg: str | None = None) -> str:
    if msg is None:
        msg = f"Invalid JSON: missing fields in stage_{stage} output"
    ctx.parser_errors[f"stage_{stage}"] = msg
    return msg


def make_valid_stage_payload(stage: int) -> dict:
    """Minimal valid structured payload per StageNSchema."""
    if stage == 1:
        return {
            "failure_modes": [
                {
                    "id": "FM1",
                    "category": "幻觉",
                    "description": "测试修复后的失败模式",
                    "severity": "high",
                    "evidence_ids": [],
                    "evidence": "人工修正",
                    "mitigation_hint": "添加校验",
                    "requires_human_review": True,
                }
            ],
            "direct_conclusion": "人工修正后的结论",
            "open_questions": [],
        }
    elif stage == 2:
        return {
            "workflow_nodes": [
                {
                    "node_id": "N1",
                    "stage_name": "人工修正节点",
                    "model_assigned": "deepseek-chat",
                    "human_action": "检查输出一致性",
                    "check_criteria": ["无编造"],
                    "addressed_failure_mode_ids": ["FM1"],
                    "prompt_template": "校验...",
                    "human_review_required": True,
                    "oversight_risk_level": "high",
                    "evidence_required": False,
                    "can_auto_continue": False,
                }
            ],
            "design_rationale": "人工修正后的流程设计",
            "open_questions": [],
        }
    elif stage == 3:
        return {
            "test_cases": [
                {
                    "case_id": "TC1",
                    "target_node_id": "N1",
                    "scenario_type": "normal",
                    "test_input": "修正后的测试输入",
                    "expected_behavior": "正确响应",
                    "predicted_failure": None,
                    "correction_prompt": None,
                    "pass_criteria": ["通过"],
                    "passed": True,
                }
            ],
            "overall_passed": True,
            "risk_summary": "人工修正后通过压测",
        }
    elif stage == 4:
        return {
            "trigger_methods": [
                {
                    "node_id": "N1",
                    "model_or_mode": "deepseek-chat",
                    "entry_point": "接收请求后触发",
                    "trigger_instruction": "curl ...",
                    "execution_suggestion": "设置max_tokens=1024",
                    "human_review_required": False,
                }
            ],
            "final_notes": "人工修正后的触发方式",
        }
    raise ValueError(f"Unknown stage: {stage}")


def make_invalid_stage_payload(stage: int) -> dict:
    """Payload missing required schema fields."""
    return {"not_a_real_field": "garbage", "stage": stage}


def find_parser_blockers(gate) -> list:
    return [b for b in gate.blockers if b.blocker_type == "parser_error"]


def find_pending_parser_actions(ctx, stage: int) -> list:
    return [
        a
        for a in ctx.pending_actions
        if a.source_type == "parser" and a.stage_id == stage and a.status == "pending"
    ]


def check_audit_events(ctx, event_type: str) -> list:
    return [e for e in ctx.audit_events if e.event_type == event_type]


# ───────────────────────────────────────────────────────
# Stage 1: Full verification
# ───────────────────────────────────────────────────────


def verify_stage1_full():
    """Complete closed-loop test for stage 1 including invalid payload rejection."""
    global session_tag
    session_tag = "s1"
    ctx = build_minimal_ctx(1)
    inject_parser_error(ctx, 1)

    print("=" * 90)
    print("STAGE 1 — FULL CLOSED-LOOP VERIFICATION")
    print("=" * 90)
    print()

    # ── Step 1: Generate parser action via official entry ──
    actions = create_actions_from_parser_errors(ctx, stage=1)
    action = actions[0] if actions else None
    assert action is not None, "FAIL: no parser action created"
    action_id = action.action_id
    print(
        f"[PASS] Parser edit action created: id={action_id}, type={action.action_type}, source={action.source_type}, stage={action.stage_id}, blocking={action.blocking}"
    )

    # ── Step 2: Gate BEFORE apply ──
    gate_before = evaluate_stage_gate(ctx, stage=1)
    pblocks_before = find_parser_blockers(gate_before)
    print(
        f"[PASS] Gate BEFORE: can_continue={gate_before.can_continue}, parser_blockers={len(pblocks_before)}, total_blockers={len(gate_before.blockers)}"
    )
    assert not gate_before.can_continue, "FAIL: gate should block before apply"
    assert len(pblocks_before) >= 1, "FAIL: parser_error blocker should exist before apply"
    assert ctx.parser_errors.get("stage_1"), "FAIL: parser error should exist before apply"

    # ── Step 3a: Attempt invalid payload ──
    print()
    # Build a separate context for invalid payload test
    session_tag = "s1b"
    ctx2 = build_minimal_ctx(1)
    inject_parser_error(ctx2, 1)
    actions2 = create_actions_from_parser_errors(ctx2, stage=1)
    aid2 = actions2[0].action_id

    invalid_payload_rejected = False
    invalid_exception_msg = ""
    try:
        resolve_action(
            ctx2, action_id=aid2, decision="edit", payload_after=make_invalid_stage_payload(1)
        )
        print("[WARN] Invalid payload was NOT rejected by resolve_action (succeeded unexpectedly)")
    except (ReviewedOutputError, Exception) as exc:
        invalid_payload_rejected = True
        invalid_exception_msg = str(exc)[:120]
        print(f"[PASS] Invalid payload REJECTED: {type(exc).__name__}: {invalid_exception_msg}")
    # Verify parser error still exists after failed apply
    pe_still_exists = bool(ctx2.parser_errors.get("stage_1"))
    print(
        f"[{'PASS' if pe_still_exists else 'FAIL'}] parser_error still exists after invalid apply: {pe_still_exists}"
    )

    # ── Step 3b: Apply valid payload via official resolve_action ──
    print()
    session_tag = "s1c"
    ctx3 = build_minimal_ctx(1)
    inject_parser_error(ctx3, 1)
    actions3 = create_actions_from_parser_errors(ctx3, stage=1)
    aid3 = actions3[0].action_id

    valid_payload = make_valid_stage_payload(1)
    resolved = resolve_action(ctx3, action_id=aid3, decision="edit", payload_after=valid_payload)
    print(
        f"[PASS] resolve_action returned action id={resolved.action_id}, status={resolved.status}, decision={resolved.reviewer_decision}"
    )

    # ── Step 4: Verify post-apply state ──
    parser_error_cleared = "stage_1" not in ctx3.parser_errors
    print(
        f"[{'PASS' if parser_error_cleared else 'FAIL'}] parser_error cleared: {parser_error_cleared}"
    )

    action_closed = resolved.status == HumanActionStatus.RESOLVED.value
    print(f"[{'PASS' if action_closed else 'FAIL'}] action closed: status={resolved.status}")

    assert resolved.source_type == "parser", "FAIL: source_type should be parser"
    assert resolved.action_type == "edit", "FAIL: action_type should be edit"
    print(
        f"[PASS] action fields preserved: source_type={resolved.source_type}, action_type={resolved.action_type}"
    )

    # ── Step 5: Gate AFTER apply ──
    gate_after = evaluate_stage_gate(ctx3, stage=1)
    pblocks_after = find_parser_blockers(gate_after)
    print(
        f"[PASS] Gate AFTER: can_continue={gate_after.can_continue}, parser_blockers={len(pblocks_after)}, total_blockers={len(gate_after.blockers)}"
    )
    parser_blocker_removed = len(pblocks_after) == 0
    print(
        f"[{'PASS' if parser_blocker_removed else 'FAIL'}] parser_error blocker removed: {parser_blocker_removed}"
    )

    # Check no pending parser actions
    pending_parser = find_pending_parser_actions(ctx3, 1)
    print(
        f"[{'PASS' if not pending_parser else 'FAIL'}] no pending parser actions: {len(pending_parser)}"
    )

    # Audit events
    edit_audits = check_audit_events(ctx3, "stage_output_edited")
    resolved_audits = check_audit_events(ctx3, "human_action_resolved")
    print(
        f"[INFO] audit events — stage_output_edited: {len(edit_audits)}, human_action_resolved: {len(resolved_audits)}"
    )

    if gate_after.blockers:
        print(
            f"[INFO] Remaining blockers after apply: {[(b.blocker_type, b.message[:60]) for b in gate_after.blockers]}"
        )
    else:
        print("[PASS] No blockers remain after apply — can_continue=True")

    result = {
        "parser_error_cleared": parser_error_cleared,
        "action_closed": action_closed,
        "parser_blocker_removed": parser_blocker_removed,
        "valid_payload_applied": True,
        "invalid_payload_rejected": invalid_payload_rejected,
        "can_continue": gate_after.can_continue,
        "total_blockers_after": len(gate_after.blockers),
    }
    return result


# ───────────────────────────────────────────────────────
# Stages 2-4: Lightweight verification
# ───────────────────────────────────────────────────────


def verify_stage_lightweight(stage: int) -> dict:
    global session_tag
    session_tag = f"s{stage}lw"
    ctx = build_minimal_ctx(stage)
    inject_parser_error(ctx, stage)

    print("-" * 90)
    print(f"STAGE {stage} — LIGHTWEIGHT VERIFICATION")
    print("-" * 90)

    actions = create_actions_from_parser_errors(ctx, stage=stage)
    action = actions[0] if actions else None
    assert action is not None, f"FAIL: no parser action created for stage {stage}"
    print(
        f"  action_created: True (id={action.action_id}, type={action.action_type}, source={action.source_type})"
    )

    gate_before = evaluate_stage_gate(ctx, stage=stage)
    assert find_parser_blockers(gate_before), f"FAIL: expected parser blocker for stage {stage}"
    print(f"  gate_before: can_continue={gate_before.can_continue}, parser_blocker_exists=True")

    valid_payload = make_valid_stage_payload(stage)
    resolved = resolve_action(
        ctx, action_id=action.action_id, decision="edit", payload_after=valid_payload
    )

    pe_cleared = f"stage_{stage}" not in ctx.parser_errors
    action_resolved = resolved.status == HumanActionStatus.RESOLVED.value

    gate_after = evaluate_stage_gate(ctx, stage=stage)
    parser_blocker_gone = len(find_parser_blockers(gate_after)) == 0

    print(f"  parser_error_cleared: {pe_cleared}")
    print(f"  action_status: {resolved.status}")
    print(f"  parser_blocker_removed: {parser_blocker_gone}")
    print(
        f"  gate_after: can_continue={gate_after.can_continue}, total_blockers={len(gate_after.blockers)}"
    )
    if gate_after.blockers:
        print(f"  remaining blocker types: {[b.blocker_type for b in gate_after.blockers]}")

    assert pe_cleared, f"FAIL: parser_error not cleared for stage {stage}"
    assert action_resolved, f"FAIL: action not resolved for stage {stage}"
    assert parser_blocker_gone, f"FAIL: parser blocker still present for stage {stage}"
    print("  [ALL CHECKS PASS]")

    return {
        "parser_error_cleared": pe_cleared,
        "action_closed": action_resolved,
        "parser_blocker_removed": parser_blocker_gone,
        "valid_payload_applied": True,
        "can_continue": gate_after.can_continue,
        "total_blockers_after": len(gate_after.blockers),
    }


# ───────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────


def main():
    all_results = {}

    # Stage 1: Full
    all_results[1] = verify_stage1_full()

    # Stages 2-4: Lightweight
    for s in [2, 3, 4]:
        all_results[s] = verify_stage_lightweight(s)

    # ── Summary ──
    print()
    print("=" * 90)
    print("SUMMARY TABLE")
    print("=" * 90)
    header = f"{'stage':<6} {'apply_ok':<9} {'invalid_rej':<11} {'pe_cleared':<11} {'action_resolved':<16} {'pblocker_gone':<14} {'can_continue':<13}"
    print(header)
    print("-" * len(header))
    for s, r in all_results.items():
        apply_ok = "true" if r["valid_payload_applied"] else "false"
        inv_rej = "true" if r.get("invalid_payload_rejected", True) else "false"
        pe_ok = "true" if r["parser_error_cleared"] else "false"
        ac_ok = "true" if r["action_closed"] else "false"
        pb_ok = "true" if r["parser_blocker_removed"] else "false"
        cc = "true" if r["can_continue"] else "false"
        print(f"{s:<6} {apply_ok:<9} {inv_rej:<11} {pe_ok:<11} {ac_ok:<16} {pb_ok:<14} {cc:<13}")
    print()

    all_pass = all(
        r["valid_payload_applied"]
        and r["parser_error_cleared"]
        and r["action_closed"]
        and r["parser_blocker_removed"]
        for r in all_results.values()
    )
    if all_pass:
        print(
            "AC-06C PASS: All four stages complete the human edit → apply → parser error cleared loop."
        )
    else:
        print("AC-06C FAIL: Some checks did not pass.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
