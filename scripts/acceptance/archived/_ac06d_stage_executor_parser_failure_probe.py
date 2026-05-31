#!/usr/bin/env python
# _ac06d_stage_executor_parser_failure_probe.py
# AC-06D: Stage executor parser failure → edit action automatic chain.
# Uses monkeypatched LLM (no real API calls), real executor.run() and
# real apply_review_gate/evaluate_stage_gate.
"""Temporary probe for AC-06D. Do not wire into production."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("DEEPSEEK_API_KEY", "probe-noop")
os.environ.setdefault("TAVILY_API_KEY", "probe-noop")
os.environ.setdefault("POSTGRES_PASSWORD", "probe-noop")

from langchain_core.messages import AIMessage  # noqa: E402

from core.models import (  # noqa: E402
    ProjectContext,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
    WorkflowNode,
)
from core.stage_readiness_service import evaluate_stage_gate  # noqa: E402
from graph.review_gate import apply_review_gate  # noqa: E402
from stages.stage_1_failure_mode import Stage1Executor  # noqa: E402
from stages.stage_2_workflow_design import Stage2Executor  # noqa: E402
from stages.stage_3_stress_test import Stage3Executor  # noqa: E402
from stages.stage_4_trigger import Stage4Executor  # noqa: E402

_EXECUTORS = {1: Stage1Executor(), 2: Stage2Executor(), 3: Stage3Executor(), 4: Stage4Executor()}

BAD_OUTPUT = (
    "This is intentionally bad output with no JSON object, no Markdown table, nothing parseable."
)


def make_fake_llm(response_text: str = BAD_OUTPUT):
    """Return a MagicMock that acts like ChatOpenAI.invoke() → AIMessage."""
    fake = MagicMock()
    fake.invoke.return_value = AIMessage(content=response_text)
    return fake


def build_base_ctx(tag: str) -> ProjectContext:
    ctx = ProjectContext(
        session_id=f"ac06d-probe-{tag}",
        research_target="test_target",
        domain="test_domain",
        goal="test_goal",
    )
    ctx.stage_1_output = Stage1Output(search_sources=["probe-dummy"])
    ctx.stage_2_output = Stage2Output()
    ctx.stage_3_output = Stage3Output()
    ctx.stage_4_output = Stage4Output()
    for s in [1, 2, 3, 4]:
        ctx.stage_output_versions[f"stage_{s}"] = 1
    return ctx


def verify_stage1_full():
    """Stage 1: full auto chain through executor.run() + apply_review_gate()."""
    print("=" * 90)
    print("STAGE 1 — FULL AUTO CHAIN (executor.run → apply_review_gate → evaluate_stage_gate)")
    print("=" * 90)
    print()

    ctx = build_base_ctx("s1")

    executor = Stage1Executor()
    import stages.base as base_module

    # Save original get_llm_for_stage
    original_get_llm = base_module.get_llm_for_stage
    base_module.get_llm_for_stage = lambda stage: make_fake_llm(BAD_OUTPUT)

    try:
        ai_text, ctx = executor.run(ctx, "Find failure modes for test system.")
    finally:
        base_module.get_llm_for_stage = original_get_llm

    print("[1] executor.run() completed")
    print(f"    ai_text returned: {repr(ai_text[:80])}")

    # Check parser error auto-written
    pe_key = "stage_1"
    pe_exists = pe_key in ctx.parser_errors
    pe_text = ctx.parser_errors.get(pe_key, "")
    print(f"[2] parser_error auto-recorded: {pe_exists} → {pe_text[:100]}")

    # Check raw output preserved
    raw_preserved = bool(ctx.stage_1_output and ctx.stage_1_output.raw_summary)
    raw_len = len(ctx.stage_1_output.raw_summary) if ctx.stage_1_output else 0
    print(f"[3] raw_summary preserved: {raw_preserved} (len={raw_len})")

    # Apply review gate (as node_stage_running does)
    ctx = apply_review_gate(ctx, stage=1, stage_output_version=1)
    print("[4] apply_review_gate(stage=1) called")

    # Check action auto-generated
    parser_actions = [a for a in ctx.pending_actions if a.source_type == "parser"]
    action = parser_actions[0] if parser_actions else None
    print(f"[5] parser actions auto-generated: {len(parser_actions)}")
    if action:
        print(f"    action_id={action.action_id}")
        print(f"    action_type={action.action_type}")
        print(f"    source_type={action.source_type}")
        print(f"    stage_id={action.stage_id}")
        print(f"    blocking={action.blocking}")
        print(f"    trigger_reason={action.trigger_reason[:100]}")

    # Stage Gate
    gate = evaluate_stage_gate(ctx, stage=1)
    pblocks = [b for b in gate.blockers if b.blocker_type == "parser_error"]
    print(
        f"[6] Stage Gate: can_continue={gate.can_continue}, parser_blockers={len(pblocks)}, total_blockers={len(gate.blockers)}"
    )
    if pblocks:
        print(
            f"    blocker: type={pblocks[0].blocker_type}, severity={pblocks[0].severity}, resolution={pblocks[0].required_resolution}"
        )

    # Verify no stage 2 was executed
    stage2_exists = ctx.stage_2_output is not None and bool(ctx.stage_2_output.workflow_nodes)
    print(f"[7] stage_2 executed: {stage2_exists} (should be False)")

    result = {
        "pe_auto_recorded": pe_exists,
        "raw_preserved": raw_preserved,
        "action_auto_created": action is not None,
        "action_type": action.action_type if action else "N/A",
        "source_type": action.source_type if action else "N/A",
        "action_blocking": action.blocking if action else False,
        "action_stage_id": action.stage_id if action else -1,
        "trigger_reason_has_error": bool(action and "parse" in action.trigger_reason.lower())
        if action
        else False,
        "gate_has_parser_blocker": len(pblocks) > 0,
        "gate_can_continue": gate.can_continue,
        "stage2_executed": stage2_exists,
        "current_state_after": str(ctx.current_state),
    }
    return result


def verify_stage_lightweight(stage: int) -> dict:
    """Lightweight auto-chain for stages 2-4."""
    print("-" * 90)
    print(f"STAGE {stage} — LIGHTWEIGHT AUTO CHAIN")
    print("-" * 90)

    ctx = build_base_ctx(f"s{stage}lw")

    # Set up minimal prerequisites so build_system_prompt doesn't crash
    if stage >= 2:
        ctx.stage_1_output.direct_conclusion = "Test conclusion"
        ctx.stage_1_output.failure_modes = []
    if stage >= 3:
        ctx.stage_2_output.workflow_nodes = [
            WorkflowNode(
                node_id="N1",
                stage_name="test",
                model_assigned="m",
                human_action="check",
                check_criteria="ok",
                failure_modes_addressed=[],
                prompt_template="test",
            )
        ]
        ctx.stage_2_output.total_stages = 1

    executor = _EXECUTORS[stage]
    import stages.base as base_module

    original_get_llm = base_module.get_llm_for_stage
    base_module.get_llm_for_stage = lambda s: make_fake_llm(BAD_OUTPUT)

    try:
        ai_text, ctx = executor.run(ctx, f"Run stage {stage} test.")
    finally:
        base_module.get_llm_for_stage = original_get_llm

    pe_key = f"stage_{stage}"
    pe_exists = pe_key in ctx.parser_errors
    raw_preserved = bool(
        getattr(ctx, f"stage_{stage}_output", None)
        and getattr(getattr(ctx, f"stage_{stage}_output"), "raw_summary", "")
    )

    # Apply review gate
    ctx = apply_review_gate(ctx, stage=stage, stage_output_version=1)

    parser_actions = [a for a in ctx.pending_actions if a.source_type == "parser"]
    action = parser_actions[0] if parser_actions else None

    gate = evaluate_stage_gate(ctx, stage=stage)
    pblocks = [b for b in gate.blockers if b.blocker_type == "parser_error"]

    print(f"  parser_error auto-recorded: {pe_exists}")
    print(f"  raw_summary preserved: {raw_preserved}")
    print(f"  parser action auto-created: {action is not None}")
    if action:
        print(
            f"    type={action.action_type}, source={action.source_type}, stage={action.stage_id}, blocking={action.blocking}"
        )
    print(f"  gate: can_continue={gate.can_continue}, parser_blockers={len(pblocks)}")

    return {
        "pe_auto_recorded": pe_exists,
        "raw_preserved": raw_preserved,
        "action_auto_created": action is not None,
        "action_type": action.action_type if action else "N/A",
        "source_type": action.source_type if action else "N/A",
        "action_blocking": action.blocking if action else False,
        "gate_has_parser_blocker": len(pblocks) > 0,
        "gate_can_continue": gate.can_continue,
    }


def main():
    results = {}
    results[1] = verify_stage1_full()

    print()
    for s in [2, 3, 4]:
        results[s] = verify_stage_lightweight(s)

    # ── Summary ──
    print()
    print("=" * 90)
    print("SUMMARY TABLE")
    print("=" * 90)
    hdr = f"{'s':<3} {'executor_used':<14} {'pe_auto':<8} {'raw_ok':<7} {'act_auto':<9} {'a_type':<7} {'s_type':<7} {'pblock':<7} {'can_cont':<9} {'next_not_run':<13}"
    print(hdr)
    print("-" * len(hdr))
    for s, r in results.items():
        print(
            f"{s:<3} {'true':<14} {str(r['pe_auto_recorded']):<8} {str(r['raw_preserved']):<7} "
            f"{str(r['action_auto_created']):<9} {r['action_type']:<7} {r['source_type']:<7} "
            f"{str(r['gate_has_parser_blocker']):<7} {str(not r['gate_can_continue']):<9} "
            f"{str(not r.get('stage2_executed', True)):<13}"
        )

    # ── Verdict ──
    print()
    all_ok = all(
        r["pe_auto_recorded"]
        and r["raw_preserved"]
        and r["action_auto_created"]
        and r["action_type"] == "edit"
        and r["source_type"] == "parser"
        and r["gate_has_parser_blocker"]
        and not r["gate_can_continue"]
        for r in results.values()
    )
    if all_ok:
        print(
            "AC-06D PASS: Stage executor auto-generates parser error → edit action → gate blocker chain."
        )
    else:
        print("AC-06D FAIL: Some automatic chain links are broken.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
