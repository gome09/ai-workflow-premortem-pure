#!/usr/bin/env python
# _ac06b_parser_action_probe.py
# AC-06B: Parser error → PendingHumanAction(edit) minimum closed-loop verification.
# Does NOT import FastAPI, Streamlit, runner, LLM, DB, Redis.
"""Temporary probe for AC-06B. Do not wire into production."""

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
    ProjectContext,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
)
from core.oversight_service import (  # noqa: E402
    create_actions_from_parser_errors,
)
from core.stage_readiness_service import (  # noqa: E402
    StageGateResult,
    evaluate_stage_gate,
)


def build_minimal_ctx() -> ProjectContext:
    """Build a minimal ProjectContext with parser errors injected and
    stage outputs initialized (to avoid spurious missing-output blockers)."""
    ctx = ProjectContext(
        session_id="ac06b-probe-session",
        research_target="probe_target",
        domain="probe_domain",
        goal="probe_goal",
    )
    # Initialize stage outputs so _collect_missing_output_blockers does not fire
    ctx.stage_1_output = Stage1Output()
    ctx.stage_2_output = Stage2Output()
    ctx.stage_3_output = Stage3Output()
    ctx.stage_4_output = Stage4Output()
    # Set output versions
    for s in [1, 2, 3, 4]:
        ctx.stage_output_versions[f"stage_{s}"] = 1
    return ctx


def inject_parser_errors(ctx: ProjectContext) -> None:
    ctx.parser_errors["stage_1"] = "Invalid JSON: missing failure_modes"
    ctx.parser_errors["stage_2"] = "Invalid JSON: missing workflow_nodes"
    ctx.parser_errors["stage_3"] = "Invalid JSON: missing test_cases"
    ctx.parser_errors["stage_4"] = "Invalid JSON: missing trigger_methods"


def verify_stage(ctx: ProjectContext, stage: int) -> dict:
    """Verify the full parser-error → action → gate chain for one stage."""
    key = f"stage_{stage}"

    # 1. Confirm parser error is recorded
    error_recorded = bool(ctx.parser_errors.get(key))
    error_text = ctx.parser_errors.get(key, "")

    # 2. Call the official oversight entry point
    actions = create_actions_from_parser_errors(ctx, stage)
    action = actions[0] if actions else None

    action_created = action is not None
    action_type = action.action_type if action else "N/A"
    source_type = action.source_type if action else "N/A"
    action_stage_id = action.stage_id if action else -1
    reason = action.trigger_reason if action else ""
    blocking = action.blocking if action else False

    # 3. Call the official Stage Gate
    gate: StageGateResult = evaluate_stage_gate(ctx, stage)

    # 4. Find parser-error blocker(s) in the gate result
    parser_blockers = [b for b in gate.blockers if b.blocker_type == "parser_error"]
    has_parser_blocker = len(parser_blockers) > 0
    blocker_type = parser_blockers[0].blocker_type if parser_blockers else "N/A"
    blocker_reason = parser_blockers[0].message if parser_blockers else ""
    blocker_action_id = parser_blockers[0].action_id if parser_blockers else "N/A"

    return {
        "stage": stage,
        "parser_error_recorded": error_recorded,
        "action_created": action_created,
        "action_type": action_type,
        "source_type": source_type,
        "stage_id_linked": action_stage_id == stage,
        "reason_included": bool(reason),
        "action_blocking": blocking,
        "gate_can_continue": gate.can_continue,
        "parser_blocker_found": has_parser_blocker,
        "blocker_type": blocker_type,
        "blocker_reason": blocker_reason,
        "blocker_action_id_match": blocker_action_id == action.action_id
        if action and parser_blockers
        else "N/A",
        "total_blockers": len(gate.blockers),
        "error_text": error_text,
    }


def main():
    ctx = build_minimal_ctx()
    inject_parser_errors(ctx)

    print("=" * 90)
    print("AC-06B: Parser error → PendingHumanAction(edit) → Stage Gate blocker")
    print("=" * 90)
    print()

    all_ok = True
    for stage in [1, 2, 3, 4]:
        r = verify_stage(ctx, stage)
        parts = [
            f"stage={stage}",
            f"parser_error_recorded={'true' if r['parser_error_recorded'] else 'false'}",
            f"action_created={'true' if r['action_created'] else 'false'}",
            f"action_type={r['action_type']}",
            f"source_type={r['source_type']}",
            f"stage_id_linked={'true' if r['stage_id_linked'] else 'false'}",
            f"reason_included={'true' if r['reason_included'] else 'false'}",
            f"gate_can_continue={'false' if not r['gate_can_continue'] else 'true'}",
            f"parser_blocker_found={'true' if r['parser_blocker_found'] else 'false'}",
            f"blocker_type={r['blocker_type']}",
        ]
        print(" ".join(parts))

        if not r["action_created"] or not r["parser_blocker_found"] or r["gate_can_continue"]:
            all_ok = False

    # ── Detailed inspection ──
    print()
    print("-" * 90)
    print("DETAILED INSPECTION (stage 1 as example)")
    print("-" * 90)
    r1 = verify_stage(ctx, 1)
    print(f"  error_text: {r1['error_text']}")
    print(f"  action_blocking: {r1['action_blocking']}")
    print(f"  blocker_reason: {r1['blocker_reason']}")
    print(f"  total_blockers: {r1['total_blockers']}")
    print(f"  blocker_action_id_match: {r1['blocker_action_id_match']}")

    # Show all blocker types for stage 1
    gate = evaluate_stage_gate(ctx, 1)
    print(f"  All blocker_types for stage 1: {[b.blocker_type for b in gate.blockers]}")
    for b in gate.blockers:
        print(
            f"    [{b.blocker_type}] {b.message} (resolution={b.required_resolution}, overridable={b.can_be_overridden_by_approval})"
        )

    print()
    print("=" * 90)
    if all_ok:
        print("AC-06B PASS: All four stages route parser errors through the full oversight chain.")
    else:
        print("AC-06B FAIL: Some parser error → action → gate links are broken.")
    print("=" * 90)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
