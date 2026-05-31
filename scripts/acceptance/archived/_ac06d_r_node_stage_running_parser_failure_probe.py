#!/usr/bin/env python
# _ac06d_r_node_stage_running_parser_failure_probe.py
# AC-06D-R: node_stage_running() automatic parser-failure chain re-verification.
# Uses monkeypatched LLM (no real API), calls real node_stage_running().
# Probe does NOT call apply_review_gate / create_review_actions_for_stage /
# create_actions_from_parser_errors directly.
"""Temporary probe for AC-06D-R. Do not wire into production."""

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
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
    WorkflowNode,
)
from core.stage_readiness_service import evaluate_stage_gate  # noqa: E402
from graph.nodes import node_stage_running  # noqa: E402

BAD_OUTPUT = (
    "This is intentionally bad output with no JSON object, "
    "no Markdown table, and no parseable structured content whatsoever."
)

LLM_CALL_TRACKER: dict = {}  # track which stages had LLM calls


def make_fake_llm(stage: int):
    """Return a MagicMock LLM that returns BAD_OUTPUT and tracks the call."""
    LLM_CALL_TRACKER[f"stage_{stage}"] = LLM_CALL_TRACKER.get(f"stage_{stage}", 0) + 1
    fake = MagicMock()
    fake.invoke.return_value = AIMessage(content=BAD_OUTPUT)
    return fake


def build_base_ctx(tag: str, state: SessionState) -> ProjectContext:
    ctx = ProjectContext(
        session_id=f"ac06dr-probe-{tag}",
        research_target="test_target",
        domain="test_domain",
        goal="test_goal",
    )
    ctx.current_state = state
    ctx.stage_1_output = Stage1Output(search_sources=["probe-dummy"])
    ctx.stage_2_output = Stage2Output()
    ctx.stage_3_output = Stage3Output()
    ctx.stage_4_output = Stage4Output()
    for s in [1, 2, 3, 4]:
        ctx.stage_output_versions[f"stage_{s}"] = 1
    return ctx


def check_parser_action(ctx, stage: int) -> dict | None:
    actions = [a for a in ctx.pending_actions if a.source_type == "parser" and a.stage_id == stage]
    if not actions:
        return None
    a = actions[0]
    return {
        "action_id": a.action_id,
        "action_type": a.action_type,
        "source_type": a.source_type,
        "stage_id": a.stage_id,
        "blocking": a.blocking,
        "trigger_reason": a.trigger_reason[:120] if a.trigger_reason else "",
    }


# ───────────────────────────────────────────────────────
# Stage 1: Full node_stage_running chain
# ───────────────────────────────────────────────────────


def verify_stage1_node():
    print("=" * 90)
    print("STAGE 1 — node_stage_running() FULL AUTO CHAIN")
    print("=" * 90)
    print()

    ctx = build_base_ctx("s1", SessionState.S1_RUNNING)
    LLM_CALL_TRACKER.clear()

    # Monkeypatch the LLM factory that stages/base.py imports
    import stages.base as base_mod

    orig_get_llm = base_mod.get_llm_for_stage
    base_mod.get_llm_for_stage = lambda s: make_fake_llm(s)

    try:
        # Single call to the real node entry — nothing else
        ctx = node_stage_running(ctx, user_input="Find failure modes.", stage=1)
    finally:
        base_mod.get_llm_for_stage = orig_get_llm

    # ── Verify results (no manual calls to gate/review/action functions) ──
    pe_exists = "stage_1" in ctx.parser_errors
    pe_text = ctx.parser_errors.get("stage_1", "")
    raw_ok = bool(ctx.stage_1_output and ctx.stage_1_output.raw_summary)
    raw_len = len(ctx.stage_1_output.raw_summary) if ctx.stage_1_output else 0
    pa = check_parser_action(ctx, 1)
    gate = evaluate_stage_gate(ctx, stage=1)
    pblocks = [b for b in gate.blockers if b.blocker_type == "parser_error"]
    state_after = (
        ctx.current_state.value if hasattr(ctx.current_state, "value") else str(ctx.current_state)
    )
    entered_review = state_after in (SessionState.S1_REVIEW.value, "s1_review")
    s2_exists = ctx.stage_2_output is not None and bool(ctx.stage_2_output.workflow_nodes)
    s2_llm_called = LLM_CALL_TRACKER.get("stage_2", 0) > 0

    print(f"parser_error auto-recorded : {pe_exists}")
    print(f"  → {pe_text[:120]}")
    print(f"raw_summary preserved      : {raw_ok} (len={raw_len})")
    print(f"parser action auto-created : {pa is not None}")
    if pa:
        print(
            f"  id={pa['action_id']} type={pa['action_type']} source={pa['source_type']} "
            f"stage={pa['stage_id']} blocking={pa['blocking']}"
        )
        print(f"  trigger_reason={pa['trigger_reason'][:100]}")
    print(f"gate parser blocker        : {len(pblocks) > 0}")
    if pblocks:
        print(
            f"  type={pblocks[0].blocker_type} severity={pblocks[0].severity} resolution={pblocks[0].required_resolution}"
        )
    print(f"gate can_continue          : {gate.can_continue}")
    print(f"current_state after        : {state_after}")
    print(f"entered review state       : {entered_review}")
    print(f"stage_2_output exists      : {s2_exists}")
    print(f"stage_2 LLM called         : {s2_llm_called}")
    print(f"total blockers             : {len(gate.blockers)}")

    return {
        "pe_auto_recorded": pe_exists,
        "raw_preserved": raw_ok,
        "action_auto_created": pa is not None,
        "action_type": pa["action_type"] if pa else "N/A",
        "source_type": pa["source_type"] if pa else "N/A",
        "action_stage_id": pa["stage_id"] if pa else -1,
        "action_blocking": pa["blocking"] if pa else False,
        "trigger_reason_ok": bool(pa and pa["trigger_reason"]) if pa else False,
        "gate_has_parser_blocker": len(pblocks) > 0,
        "gate_can_continue": gate.can_continue,
        "entered_review_state": entered_review,
        "stage2_executed": s2_exists,
        "stage2_llm_called": s2_llm_called,
        "current_state_after": state_after,
    }


# ───────────────────────────────────────────────────────
# Stages 2-4: Lightweight node_stage_running chain
# ───────────────────────────────────────────────────────


def verify_stage_lightweight_node(stage: int) -> dict:
    print("-" * 90)
    print(f"STAGE {stage} — node_stage_running() LIGHTWEIGHT CHAIN")
    print("-" * 90)

    running_state = {
        2: SessionState.S2_RUNNING,
        3: SessionState.S3_RUNNING,
        4: SessionState.S4_RUNNING,
    }[stage]
    review_state = {
        2: SessionState.S2_REVIEW,
        3: SessionState.S3_REVIEW,
        4: SessionState.S4_REVIEW,
    }[stage]

    ctx = build_base_ctx(f"s{stage}lw", running_state)

    # Set minimal prerequisites for build_system_prompt
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

    import stages.base as base_mod

    orig_get_llm = base_mod.get_llm_for_stage

    def staged_fake(s):
        LLM_CALL_TRACKER[f"stage_{s}"] = LLM_CALL_TRACKER.get(f"stage_{s}", 0) + 1
        fake = MagicMock()
        fake.invoke.return_value = AIMessage(content=BAD_OUTPUT)
        return fake

    base_mod.get_llm_for_stage = staged_fake
    LLM_CALL_TRACKER.clear()

    try:
        ctx = node_stage_running(ctx, user_input=f"Run stage {stage}.", stage=stage)
    finally:
        base_mod.get_llm_for_stage = orig_get_llm

    pe_key = f"stage_{stage}"
    pe_exists = pe_key in ctx.parser_errors
    raw_ok = bool(
        getattr(ctx, f"stage_{stage}_output", None)
        and getattr(getattr(ctx, f"stage_{stage}_output"), "raw_summary", "")
    )
    pa = check_parser_action(ctx, stage)
    gate = evaluate_stage_gate(ctx, stage)
    pblocks = [b for b in gate.blockers if b.blocker_type == "parser_error"]
    state_after = (
        ctx.current_state.value if hasattr(ctx.current_state, "value") else str(ctx.current_state)
    )
    entered_review = state_after == review_state.value

    next_llm_key = f"stage_{stage + 1}"
    next_llm_called = stage < 4 and LLM_CALL_TRACKER.get(next_llm_key, 0) > 0

    print(f"  parser_error auto-recorded : {pe_exists}")
    print(f"  raw_summary preserved      : {raw_ok}")
    print(f"  parser action auto-created : {pa is not None}")
    if pa:
        print(
            f"    type={pa['action_type']} source={pa['source_type']} "
            f"stage={pa['stage_id']} blocking={pa['blocking']}"
        )
    print(f"  gate parser blocker        : {len(pblocks) > 0}")
    print(f"  gate can_continue          : {gate.can_continue}")
    print(f"  current_state after        : {state_after}")
    print(f"  entered review state       : {entered_review}")
    print(f"  next_stage LLM called      : {next_llm_called}")

    return {
        "pe_auto_recorded": pe_exists,
        "raw_preserved": raw_ok,
        "action_auto_created": pa is not None,
        "action_type": pa["action_type"] if pa else "N/A",
        "source_type": pa["source_type"] if pa else "N/A",
        "action_blocking": pa["blocking"] if pa else False,
        "gate_has_parser_blocker": len(pblocks) > 0,
        "gate_can_continue": gate.can_continue,
        "entered_review_state": entered_review,
        "next_stage_llm_called": next_llm_called,
    }


# ───────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────


def main():
    results = {}

    results[1] = verify_stage1_node()

    print()
    for s in [2, 3, 4]:
        results[s] = verify_stage_lightweight_node(s)

    # ── Summary ──
    print()
    print("=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)
    hdr = (
        f"{'s':<3} {'node_entry':<12} {'fake_llm':<9} {'no_manual_rg':<12} "
        f"{'pe_auto':<8} {'raw_ok':<7} {'act_auto':<9} "
        f"{'pblock':<7} {'can_cont':<9} {'review_st':<10} {'next_not':<9}"
    )
    print(hdr)
    print("-" * len(hdr))
    for s, r in results.items():
        print(
            f"{s:<3} {'true':<12} {'true':<9} {'true':<12} "
            f"{str(r['pe_auto_recorded']):<8} {str(r['raw_preserved']):<7} "
            f"{str(r['action_auto_created']):<9} {str(r['gate_has_parser_blocker']):<7} "
            f"{str(not r['gate_can_continue']):<9} "
            f"{str(r.get('entered_review_state', 'N/A')):<10} "
            f"{str(not r.get('stage2_executed', True)):<9}"
        )
    print()

    all_ok = all(
        r["pe_auto_recorded"]
        and r["raw_preserved"]
        and r["action_auto_created"]
        and r["action_type"] == "edit"
        and r["source_type"] == "parser"
        and r["gate_has_parser_blocker"]
        and not r["gate_can_continue"]
        and r.get("entered_review_state", False)
        for r in results.values()
    )
    if all_ok:
        print("AC-06D-R PASS: node_stage_running() auto-completes the full parser-failure chain.")
    else:
        print("AC-06D-R FAIL: Some node-level automatic chain links are broken.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
