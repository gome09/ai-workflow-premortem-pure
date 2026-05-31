# core/gates/engine.py
from __future__ import annotations

from typing import Any

from core.gates.rules import registered_rules
from core.models import ProjectContext
from core.stage_readiness_service import StageGateResult, _current_version


def build_gate_trace_metadata(
    *,
    stage: int,
    rules_evaluated: list[str],
    result: StageGateResult,
) -> dict[str, Any]:
    """Build trace metadata for callers that want an auditable gate snapshot.

    `evaluate_stage_gate()` remains non-mutating. API/service callers may
    append this metadata to LLMTrace separately when they need an explicit
    gate trace.
    """
    return {
        "stage": stage,
        "stage_output_version": result.stage_output_version,
        "rules_evaluated": rules_evaluated,
        "blockers_count": len(result.blockers),
        "blocker_ids": [blocker.blocker_id for blocker in result.blockers],
        "blocker_rule_ids": [blocker.rule_id for blocker in result.blockers],
        "can_continue": result.can_continue,
    }


def append_gate_evaluation_trace(
    ctx: ProjectContext,
    *,
    result: StageGateResult,
    rules_evaluated: list[str] | None = None,
    node_name: str = "gate_engine",
):
    """Append an optional gate trace without changing gate semantics."""
    from core.traces import append_llm_trace, create_llm_trace

    rules = rules_evaluated or sorted(
        {blocker.rule_id for blocker in result.blockers if blocker.rule_id}
    )
    trace = create_llm_trace(
        ctx,
        stage=result.stage_id,
        node_name=node_name,
        trace_type="gate",
        parser_status="not_applicable",
        metadata=build_gate_trace_metadata(
            stage=result.stage_id,
            rules_evaluated=rules,
            result=result,
        ),
    )
    return append_llm_trace(ctx, trace)


def evaluate_stage_gate(ctx: ProjectContext, stage: int) -> StageGateResult:
    if stage < 1 or stage > 4:
        raise ValueError(f"stage must be 1..4, got {stage}")

    blockers = []
    evaluated_rule_ids: list[str] = []
    for rule in registered_rules():
        if rule.applies_to(stage):
            evaluated_rule_ids.append(rule.rule_id)
            blockers.extend(rule.evaluate(ctx, stage))

    deduped = []
    seen: set[str] = set()
    for blocker in blockers:
        if blocker.blocker_id in seen:
            continue
        seen.add(blocker.blocker_id)
        deduped.append(blocker)

    result = StageGateResult(
        stage_id=stage,
        stage_output_version=_current_version(ctx, stage),
        can_continue=not deduped,
        blockers=deduped,
    )
    # Keep rules evaluated available for optional trace consumers without
    # mutating ProjectContext during normal readiness calculations.
    result.__dict__["_rules_evaluated"] = evaluated_rule_ids
    return result
