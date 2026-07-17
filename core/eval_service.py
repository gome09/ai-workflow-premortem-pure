# core/eval_service.py
from __future__ import annotations

from datetime import datetime

from core.audit_service import append_audit_event
from core.models import EvalCase, ProjectContext


def _eval_key(case: EvalCase) -> tuple[str | None, str, str]:
    return (case.target_node_id, case.scenario_type, case.input_payload)


def _node_failure_mode_map(ctx: ProjectContext) -> dict[str, list[str]]:
    if not ctx.stage_2_output:
        return {}
    return {
        node.node_id: list(dict.fromkeys(node.failure_modes_addressed or []))
        for node in ctx.stage_2_output.workflow_nodes
    }


def sync_eval_cases_from_stage3(ctx: ProjectContext) -> int:
    """把 Stage 3 压测结果同步为可积累 EvalCase。

    幂等键：target_node_id + scenario_type + input_payload。
    """
    if not ctx.stage_3_output:
        return 0

    node_to_failure_modes = _node_failure_mode_map(ctx)
    existing = {_eval_key(case) for case in ctx.eval_cases}
    added = 0
    for result in ctx.stage_3_output.test_results:
        case = EvalCase(
            session_id=ctx.session_id,
            stage_id=3,
            target_node_id=result.tested_node_id,
            covered_failure_mode_ids=node_to_failure_modes.get(result.tested_node_id, []),
            scenario_type=result.scenario_type,
            input_payload=result.test_input,
            expected_behavior=result.ai_output,
            pass_criteria=list(result.pass_criteria or []),
            actual_output=None,
            passed=result.passed,
        )
        if _eval_key(case) in existing:
            continue
        ctx.eval_cases.append(case)
        existing.add(_eval_key(case))
        added += 1

    if added:
        append_audit_event(
            ctx,
            actor="system",
            event_type="eval_cases_synced",
            target_type="eval_case",
            target_id="stage_3",
            after={"added": added},
            metadata={"stage_id": 3},
        )
    return added


def score_eval_case(
    ctx: ProjectContext,
    *,
    eval_id: str,
    human_score: int | None = None,
    human_comment: str = "",
    passed: bool | None = None,
    actual_output: str | None = None,
) -> EvalCase:
    for case in ctx.eval_cases:
        if case.eval_id != eval_id:
            continue
        before = case.model_dump(mode="json")
        if human_score is not None:
            if human_score < 1 or human_score > 5:
                raise ValueError("human_score must be between 1 and 5")
            case.human_score = human_score
        case.human_comment = human_comment
        case.passed = passed
        if actual_output is not None:
            case.actual_output = actual_output
        case.scored_at = datetime.utcnow()
        append_audit_event(
            ctx,
            actor="user",
            event_type="eval_case_scored",
            target_type="eval_case",
            target_id=case.eval_id,
            before=before,
            after=case,
            metadata={"human_score": human_score, "passed": passed},
        )
        return case
    raise ValueError(f"Eval case not found: {eval_id}")


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def build_eval_summary(ctx: ProjectContext) -> dict:
    cases = ctx.eval_cases
    total = len(cases)
    passed_count = sum(1 for case in cases if case.passed is True)
    failed_count = sum(1 for case in cases if case.passed is False)
    human_scored_count = sum(1 for case in cases if case.human_score is not None)
    scenario_counts: dict[str, int] = {}
    covered_nodes = set()
    covered_failure_modes = set()

    for case in cases:
        scenario_counts[case.scenario_type] = scenario_counts.get(case.scenario_type, 0) + 1
        if case.target_node_id:
            covered_nodes.add(case.target_node_id)
        covered_failure_modes.update(case.covered_failure_mode_ids or [])

    all_failure_modes = {
        fm.id for fm in (ctx.stage_1_output.failure_modes if ctx.stage_1_output else [])
    }

    high_risk_failure_modes = {
        fm.id
        for fm in (ctx.stage_1_output.failure_modes if ctx.stage_1_output else [])
        if str(fm.severity).lower() in {"high", "critical"}
    }
    high_risk_nodes = set()
    if ctx.stage_2_output:
        for node in ctx.stage_2_output.workflow_nodes:
            if high_risk_failure_modes.intersection(set(node.failure_modes_addressed or [])):
                high_risk_nodes.add(node.node_id)

    human_actions = ctx.pending_actions
    resolved_actions = [a for a in human_actions if a.status == "resolved"]
    rejected_actions = [a for a in resolved_actions if a.reviewer_decision == "reject"]

    total_flags = len(ctx.flagged_items)
    closed_flags = sum(1 for flag in ctx.flagged_items if flag.status != "pending")

    stage_count = 4
    parser_error_count = len([k for k in ctx.parser_errors if k.startswith("stage_")])

    failure_modes = ctx.stage_1_output.failure_modes if ctx.stage_1_output else []
    evidence_referenced = [fm for fm in failure_modes if (getattr(fm, "evidence_ids", []) or [])]

    runs = ctx.eval_runs
    completed_runs = [run for run in runs if run.status == "completed"]
    failed_runs = [run for run in runs if run.judge_result == "failed" or run.status == "failed"]
    needs_review_runs = [run for run in runs if run.judge_result == "needs_review"]

    return {
        "total_eval_cases": total,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "human_scored_count": human_scored_count,
        "total_eval_runs": len(runs),
        "completed_eval_runs": len(completed_runs),
        "failed_eval_runs": len(failed_runs),
        "needs_review_eval_runs": len(needs_review_runs),
        "scenario_counts": scenario_counts,
        "covered_node_count": len(covered_nodes),
        "failure_mode_coverage": {
            "total_failure_modes": len(all_failure_modes),
            "covered_failure_modes": len(covered_failure_modes.intersection(all_failure_modes)),
            "coverage_rate": _rate(
                len(covered_failure_modes.intersection(all_failure_modes)), len(all_failure_modes)
            ),
        },
        "high_risk_node_coverage": {
            "total_high_risk_nodes": len(high_risk_nodes),
            "covered_high_risk_nodes": len(covered_nodes.intersection(high_risk_nodes)),
            "coverage_rate": _rate(
                len(covered_nodes.intersection(high_risk_nodes)), len(high_risk_nodes)
            ),
        },
        "human_rejection_rate": _rate(len(rejected_actions), len(resolved_actions)),
        "parser_success_rate": _rate(stage_count - parser_error_count, stage_count),
        "flag_closure_rate": _rate(closed_flags, total_flags),
        "evidence_reference_rate": _rate(len(evidence_referenced), len(failure_modes)),
    }
