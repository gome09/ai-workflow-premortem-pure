#!/usr/bin/env python
# _ac06c_r_parser_edit_atomicity_probe.py
# AC-06C-R: Parser edit apply atomicity fix re-verification.
# Does NOT import FastAPI, Streamlit, runner, LLM, DB, Redis.
"""Temporary probe for AC-06C-R. Do not wire into production."""

from __future__ import annotations

import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("DEEPSEEK_API_KEY", "probe-noop")
os.environ.setdefault("TAVILY_API_KEY", "probe-noop")
os.environ.setdefault("POSTGRES_PASSWORD", "probe-noop")

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
from core.reviewed_output_service import ReviewedOutputError  # noqa: E402
from core.stage_readiness_service import evaluate_stage_gate  # noqa: E402
from graph.transition_policy import TransitionPolicyError  # noqa: E402

_tag = ""


def build_minimal_ctx() -> ProjectContext:
    ctx = ProjectContext(
        session_id=f"ac06cr-probe-{_tag}",
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


def valid_payload(stage: int) -> dict:
    sp = {
        1: {
            "failure_modes": [
                {
                    "id": "FM1",
                    "category": "test",
                    "description": "desc",
                    "severity": "high",
                    "evidence_ids": [],
                    "evidence": "test",
                    "mitigation_hint": None,
                    "requires_human_review": True,
                }
            ],
            "direct_conclusion": "valid conclusion",
            "open_questions": [],
        },
        2: {
            "workflow_nodes": [
                {
                    "node_id": "N1",
                    "stage_name": "test",
                    "model_assigned": "m",
                    "human_action": "check",
                    "check_criteria": ["c1"],
                    "addressed_failure_mode_ids": ["FM1"],
                    "prompt_template": "",
                    "human_review_required": False,
                    "oversight_risk_level": "low",
                    "evidence_required": False,
                    "can_auto_continue": True,
                }
            ],
            "design_rationale": "",
            "open_questions": [],
        },
        3: {
            "test_cases": [
                {
                    "case_id": "TC1",
                    "target_node_id": "N1",
                    "scenario_type": "normal",
                    "test_input": "in",
                    "expected_behavior": "ok",
                    "predicted_failure": None,
                    "correction_prompt": None,
                    "pass_criteria": ["ok"],
                    "passed": True,
                }
            ],
            "overall_passed": True,
            "risk_summary": "",
        },
        4: {
            "trigger_methods": [
                {
                    "node_id": "N1",
                    "model_or_mode": "m",
                    "entry_point": "entry",
                    "trigger_instruction": "curl",
                    "execution_suggestion": "",
                    "human_review_required": False,
                }
            ],
            "final_notes": "",
        },
    }
    return sp[stage]


def invalid_no_schema_key() -> dict:
    return {"not_a_real_field": "garbage", "text": "no schema keys here"}


def invalid_bad_schema_value() -> dict:
    """Has schema key but Pydantic-invalid value: failure_modes is a string, not a list."""
    return {
        "failure_modes": "not-a-list-should-be-array",
        "direct_conclusion": "invalid payload with schema key but wrong type",
        "open_questions": [],
    }


def find_parser_blockers(gate) -> list:
    return [b for b in gate.blockers if b.blocker_type == "parser_error"]


# ───────────────────────────────────────────────────────
# Stage 1: Full atomicity tests
# ───────────────────────────────────────────────────────


def test_stage1_valid():
    global _tag
    _tag = "s1v"
    ctx = build_minimal_ctx()
    ctx.parser_errors["stage_1"] = "Invalid JSON: missing failure_modes"
    actions = create_actions_from_parser_errors(ctx, stage=1)
    aid = actions[0].action_id
    version_before = ctx.stage_output_versions.get("stage_1", 1)

    resolved = resolve_action(ctx, action_id=aid, decision="edit", payload_after=valid_payload(1))
    return {
        "case": "valid",
        "payload_applied": True,
        "action_status": resolved.status,
        "parser_error_cleared": "stage_1" not in ctx.parser_errors,
        "version_changed": ctx.stage_output_versions.get("stage_1", 1) != version_before,
        "parser_blocker_gone": len(find_parser_blockers(evaluate_stage_gate(ctx, 1))) == 0,
        "resolved_audit_count": len(
            [e for e in ctx.audit_events if e.event_type == "human_action_resolved"]
        ),
        "exception": None,
    }


def test_stage1_invalid_no_key():
    global _tag
    _tag = "s1nk"
    ctx = build_minimal_ctx()
    ctx.parser_errors["stage_1"] = "Invalid JSON: missing failure_modes"
    actions = create_actions_from_parser_errors(ctx, stage=1)
    aid = actions[0].action_id
    action_before = actions[0].model_dump(mode="json")
    version_before = ctx.stage_output_versions.get("stage_1", 1)

    exc_type = None
    action_stays_pending = False
    try:
        resolve_action(ctx, action_id=aid, decision="edit", payload_after=invalid_no_schema_key())
    except TransitionPolicyError:
        exc_type = "TransitionPolicyError"
        # Action should still be pending after exception
        still_pending = any(
            a.action_id == aid and a.status == HumanActionStatus.PENDING.value
            for a in ctx.pending_actions
        )
        action_stays_pending = still_pending
    except Exception as e:
        exc_type = type(e).__name__

    return {
        "case": "invalid_no_schema_key",
        "payload_applied": False,
        "action_status": "pending" if action_stays_pending else "unknown",
        "parser_error_cleared": "stage_1" not in ctx.parser_errors,
        "version_changed": ctx.stage_output_versions.get("stage_1", 1) != version_before,
        "parser_error_kept": "stage_1" in ctx.parser_errors,
        "resolved_audit_count": len(
            [e for e in ctx.audit_events if e.event_type == "human_action_resolved"]
        ),
        "exception": exc_type,
        "action_stays_pending": action_stays_pending,
    }


def test_stage1_invalid_bad_value():
    """Payload has failure_modes key but value is a string (not list) — fails Pydantic."""
    global _tag
    _tag = "s1bv"
    ctx = build_minimal_ctx()
    ctx.parser_errors["stage_1"] = "Invalid JSON: missing failure_modes"
    actions = create_actions_from_parser_errors(ctx, stage=1)
    aid = actions[0].action_id
    version_before = ctx.stage_output_versions.get("stage_1", 1)
    stage_output_before = ctx.stage_1_output.model_dump(mode="json") if ctx.stage_1_output else None

    exc_type = None
    exc_msg = ""
    action_stays_pending = False
    parser_error_kept = False
    output_unchanged = False

    try:
        resolve_action(
            ctx, action_id=aid, decision="edit", payload_after=invalid_bad_schema_value()
        )
    except ReviewedOutputError as e:
        exc_type = "ReviewedOutputError"
        exc_msg = str(e)[:150]
        still_pending = any(
            a.action_id == aid and a.status == HumanActionStatus.PENDING.value
            for a in ctx.pending_actions
        )
        action_stays_pending = still_pending
        parser_error_kept = "stage_1" in ctx.parser_errors
        output_unchanged = ctx.stage_1_output.model_dump(mode="json") == stage_output_before
    except TransitionPolicyError as e:
        exc_type = "TransitionPolicyError"
        exc_msg = str(e)[:150]
    except Exception as e:
        exc_type = type(e).__name__
        exc_msg = str(e)[:150]

    version_unchanged = ctx.stage_output_versions.get("stage_1", 1) == version_before

    return {
        "case": "invalid_bad_schema_value",
        "payload_applied": False,
        "action_status": "pending" if action_stays_pending else "changed",
        "parser_error_cleared": "stage_1" not in ctx.parser_errors,
        "parser_error_kept": parser_error_kept,
        "version_changed": not version_unchanged,
        "output_unchanged": output_unchanged,
        "resolved_audit_count": len(
            [e for e in ctx.audit_events if e.event_type == "human_action_resolved"]
        ),
        "exception": exc_type,
        "exc_msg": exc_msg,
        "action_stays_pending": action_stays_pending,
    }


# ───────────────────────────────────────────────────────
# Stages 2-4: Lightweight valid-payload verification
# ───────────────────────────────────────────────────────


def test_stage_lightweight(stage: int) -> dict:
    global _tag
    _tag = f"s{stage}lw"
    ctx = build_minimal_ctx()
    ctx.parser_errors[f"stage_{stage}"] = f"Invalid JSON for stage {stage}"
    actions = create_actions_from_parser_errors(ctx, stage=stage)
    aid = actions[0].action_id

    resolved = resolve_action(
        ctx, action_id=aid, decision="edit", payload_after=valid_payload(stage)
    )
    gate = evaluate_stage_gate(ctx, stage)
    return {
        "stage": stage,
        "action_resolved": resolved.status == HumanActionStatus.RESOLVED.value,
        "parser_error_cleared": f"stage_{stage}" not in ctx.parser_errors,
        "parser_blocker_gone": len(find_parser_blockers(gate)) == 0,
    }


# ───────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────


def main():
    print("=" * 90)
    print("AC-06C-R: RESOLVE_ACTION ATOMICITY FIX — VERIFICATION")
    print("=" * 90)
    print()

    # ── Stage 1: three cases ──
    print("─" * 90)
    print("STAGE 1 — ATOMICITY TESTS")
    print("─" * 90)

    r_valid = test_stage1_valid()
    print("\n  [VALID PAYLOAD]")
    print(
        f"    action_status={r_valid['action_status']} | pe_cleared={r_valid['parser_error_cleared']} | "
        f"pblocker_gone={r_valid['parser_blocker_gone']} | "
        f"audit_resolved={r_valid['resolved_audit_count']} | "
        f"version_changed={r_valid['version_changed']}"
    )

    r_nokey = test_stage1_invalid_no_key()
    print("\n  [INVALID — NO SCHEMA KEY]")
    print(
        f"    exception={r_nokey['exception']} | action_stays_pending={r_nokey['action_stays_pending']} | "
        f"pe_kept={r_nokey['parser_error_kept']} | "
        f"audit_resolved={r_nokey['resolved_audit_count']}"
    )

    r_badval = test_stage1_invalid_bad_value()
    print("\n  [INVALID — BAD SCHEMA VALUE (failure_modes as string, not list)]")
    print(
        f"    exception={r_badval['exception']} | action_stays_pending={r_badval['action_stays_pending']} | "
        f"pe_kept={r_badval['parser_error_kept']} | "
        f"output_unchanged={r_badval['output_unchanged']} | "
        f"version_changed={r_badval['version_changed']} | "
        f"audit_resolved={r_badval['resolved_audit_count']}"
    )
    if r_badval["exc_msg"]:
        print(f"    exc_msg: {r_badval['exc_msg']}")

    # ── Stages 2-4 ──
    print()
    print("─" * 90)
    print("STAGES 2-4 — LIGHTWEIGHT VALID-PAYLOAD VERIFICATION")
    print("─" * 90)

    lw_results = {}
    for s in [2, 3, 4]:
        r = test_stage_lightweight(s)
        lw_results[s] = r
        print(
            f"  stage={s} action_resolved={r['action_resolved']} "
            f"pe_cleared={r['parser_error_cleared']} "
            f"pblocker_gone={r['parser_blocker_gone']}"
        )

    # ── Summary ──
    print()
    print("=" * 90)
    print("SUMMARY TABLE")
    print("=" * 90)
    hdr = f"{'stage':<6} {'valid_applied':<14} {'no_key_rej':<12} {'bad_val_rej':<12} {'stays_pending':<14} {'pe_kept_bad':<12} {'out_unch_bad':<12} {'no_res_audit_bad':<17}"
    print(hdr)
    print("-" * len(hdr))
    # Stage 1 row
    print(
        f"{'1':<6} {'true':<14} {str(r_nokey['exception'] == 'TransitionPolicyError'):<12} "
        f"{str(r_badval['exception'] == 'ReviewedOutputError'):<12} "
        f"{str(r_badval['action_stays_pending']):<14} "
        f"{str(r_badval['parser_error_kept']):<12} "
        f"{str(r_badval.get('output_unchanged', 'N/A')):<12} "
        f"{str(r_badval['resolved_audit_count'] == 0):<17}"
    )
    for s in [2, 3, 4]:
        r = lw_results[s]
        print(
            f"{s:<6} {str(r['action_resolved']):<14} {'N/A':<12} {'N/A':<12} {'N/A':<14} {'N/A':<12} {'N/A':<12} {'N/A':<17}"
        )

    # ── Verdict ──
    print()
    all_ok = (
        r_valid["action_status"] == "resolved"
        and r_valid["parser_error_cleared"]
        and r_nokey["exception"] == "TransitionPolicyError"
        and r_nokey["action_stays_pending"]
        and r_nokey["parser_error_kept"]
        and r_badval["exception"] == "ReviewedOutputError"
        and r_badval["action_stays_pending"]
        and r_badval["parser_error_kept"]
        and r_badval["resolved_audit_count"] == 0
        and r_badval.get("output_unchanged", False)
        and all(
            lw_results[s]["action_resolved"]
            and lw_results[s]["parser_error_cleared"]
            and lw_results[s]["parser_blocker_gone"]
            for s in [2, 3, 4]
        )
    )
    if all_ok:
        print("AC-06C-R PASS: resolve_action atomicity is correct.")
    else:
        print("AC-06C-R FAIL: some atomicity checks did not pass.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
