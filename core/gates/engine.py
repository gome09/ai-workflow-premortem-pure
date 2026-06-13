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


def evaluate_stage_gate(
    ctx: ProjectContext,
    stage: int,
    detailed: bool = False,
) -> StageGateResult:
    """Evaluate the gate for *stage* and return a StageGateResult.

    Parameters
    ----------
    ctx:
        Current project context.
    stage:
        Stage number (1–4).
    detailed:
        When ``False`` (default) the function is identical to the previous
        implementation — no extra allocations, no GateReport attached.
        When ``True`` per-rule results are collected and a ``GateReport``
        is attached to ``result.report``.
    """
    if stage < 1 or stage > 4:
        raise ValueError(f"stage must be 1..4, got {stage}")

    # Imports deferred to avoid circular imports at module load time.
    if detailed:
        from core.gates.report import (
            GateReport,
            _display_name,
            _RuleEvalRecord,
            build_report,
        )
        from core.gates.risk_profile import classify_project_risk

    blockers = []
    evaluated_rule_ids: list[str] = []
    rule_records: list[Any] = []  # only populated when detailed=True

    for rule in registered_rules():
        if not rule.applies_to(stage):
            if detailed:
                rule_records.append(
                    _RuleEvalRecord(
                        rule_id=rule.rule_id,
                        display_name=_display_name(rule.rule_id),
                        status="skipped",
                        skipped_reason=f"Rule does not apply to stage {stage}.",
                    )
                )
            continue

        evaluated_rule_ids.append(rule.rule_id)
        rule_blockers = rule.evaluate(ctx, stage)

        if detailed:
            if rule_blockers:
                # One record per blocking instance; first blocker wins for
                # severity/reason. If a rule emits multiple blockers we merge
                # them into a single "blocked" record so the report is per-rule.
                first = rule_blockers[0]
                rule_records.append(
                    _RuleEvalRecord(
                        rule_id=rule.rule_id,
                        display_name=_display_name(rule.rule_id),
                        status="blocked",
                        severity=getattr(first, "severity", None),
                        reason=getattr(first, "message", None),
                    )
                )
            else:
                rule_records.append(
                    _RuleEvalRecord(
                        rule_id=rule.rule_id,
                        display_name=_display_name(rule.rule_id),
                        status="passed",
                    )
                )

        blockers.extend(rule_blockers)

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

    if detailed:
        risk_tier, _ = classify_project_risk(ctx)
        report: GateReport = build_report(
            session_id=getattr(ctx, "session_id", "") or "",
            stage=stage,
            risk_profile=str(risk_tier),
            rule_records=rule_records,
            overall_passed=not deduped,
        )
        result.__dict__["report"] = report
    else:
        result.__dict__["report"] = None

    return result
