from __future__ import annotations

from typing import Any

from core.audit_service import append_audit_event
from core.eval_dataset_service import create_dataset
from core.models import EvalCase, EvalDataset, LLMTrace, ProjectContext
from core.traces import append_llm_trace, create_llm_trace
from core.version import APP_VERSION

TRACE_BACKFILL_POLICY_VERSION = APP_VERSION
TRACE_BACKFILL_TAG = "production_trace"
PARSER_FAILURE_STATUSES = {"failed", "error", "invalid"}
SAFETY_OK_STATUSES = {"", "not_scanned", "passed", "ok", "clear", "safe"}


def is_trace_backfill_eligible(trace: LLMTrace) -> bool:
    """Return whether a trace should be converted into a regression EvalCase.

    This helper is deliberately pure-read and is shared by the trace backfill
    service, Stage 3 GateRule, report summary, and non-executed contract tests.
    It does not create EvalCases or datasets.
    """
    parser_failed = str(trace.parser_status or "").lower() in PARSER_FAILURE_STATUSES
    safety_status = str(trace.safety_status or "").lower()
    safety_failed = safety_status not in SAFETY_OK_STATUSES
    runtime_failed = bool(trace.error_type or trace.error_message)
    return bool(runtime_failed or parser_failed or safety_failed)


def _trace_by_id(ctx: ProjectContext, trace_id: str) -> LLMTrace:
    for trace in getattr(ctx, "llm_traces", []) or []:
        if trace.trace_id == trace_id:
            return trace
    raise ValueError(f"Trace not found: {trace_id}")


def _scenario_for_trace(trace: LLMTrace) -> str:
    text = " ".join(
        [
            str(trace.trace_type or ""),
            str(trace.parser_status or ""),
            str(trace.safety_status or ""),
            str(trace.error_type or ""),
            str(trace.error_message or ""),
        ]
    ).lower()
    if "parser" in text or str(trace.parser_status or "").lower() in PARSER_FAILURE_STATUSES:
        return "parser"
    if (
        trace.trace_type == "safety"
        or "safety" in text
        or str(trace.safety_status or "").lower() not in SAFETY_OK_STATUSES
    ):
        return "safety"
    return "production_failure"


def _input_for_trace(trace: LLMTrace) -> str:
    metadata = dict(trace.metadata or {})
    prompt_preview = metadata.get("prompt_preview") or metadata.get("input_preview") or ""
    return "\n".join(
        [
            f"Trace ID: {trace.trace_id}",
            f"Trace type: {trace.trace_type}",
            f"Stage: {trace.stage}",
            f"Node: {trace.node_name}",
            f"Parser status: {trace.parser_status}",
            f"Safety status: {trace.safety_status}",
            f"Error type: {trace.error_type or '-'}",
            f"Error message: {trace.error_message or '-'}",
            "",
            "Prompt/Input preview:",
            str(prompt_preview or "(not captured in trace metadata)"),
        ]
    )


def convert_trace_to_eval_case(
    ctx: ProjectContext,
    *,
    trace_id: str,
    expected_behavior: str | None = None,
    target_node_id: str | None = None,
) -> EvalCase:
    trace = _trace_by_id(ctx, trace_id)
    for case in getattr(ctx, "eval_cases", []) or []:
        if getattr(case, "source_trace_id", None) == trace_id:
            return case

    scenario = _scenario_for_trace(trace)
    eval_case = EvalCase(
        session_id=ctx.session_id,
        stage_id=trace.stage or 3,
        target_node_id=target_node_id,
        scenario_type=scenario,  # type: ignore[arg-type]
        source_type="production_trace"
        if scenario == "production_failure"
        else "parser_error"
        if scenario == "parser"
        else "safety_finding",
        source_trace_id=trace.trace_id,
        source_ref_id=trace.trace_id,
        input_payload=_input_for_trace(trace),
        expected_behavior=expected_behavior
        or "The workflow should handle this trace failure deterministically, avoid unsafe output, and require human review when confidence is insufficient.",
        pass_criteria=[
            "The failure mode is reproduced or explicitly guarded against.",
            "Parser/safety errors must not be silently ignored.",
            "High-risk recovery paths must require human review.",
        ],
        metadata={
            "trace_type": trace.trace_type,
            "node_name": trace.node_name,
            "parser_status": trace.parser_status,
            "safety_status": trace.safety_status,
            "error_type": trace.error_type,
            "runtime_validation": "deferred_by_instruction",
            "trace_backfill_policy_version": TRACE_BACKFILL_POLICY_VERSION,
        },
    )
    ctx.eval_cases.append(eval_case)
    append_audit_event(
        ctx,
        actor="system",
        event_type="trace_backfilled_to_eval_case",
        target_type="eval_case",
        target_id=eval_case.eval_id,
        after=eval_case,
        metadata={"trace_id": trace_id, "scenario_type": scenario},
    )
    append_llm_trace(
        ctx,
        create_llm_trace(
            ctx,
            stage=trace.stage or 3,
            node_name="trace_backfill_to_eval_case",
            trace_type="eval",
            parser_status="not_applicable",
            metadata={"source_trace_id": trace_id, "eval_id": eval_case.eval_id},
        ),
    )
    return eval_case


def create_dataset_from_failed_traces(
    ctx: ProjectContext,
    *,
    trace_ids: list[str] | None = None,
    name: str = "Trace backfill regression dataset",
    description: str = "EvalCases generated from failed/parser/safety traces for regression gating.",
    version: str = "0.1",
    owner: str = "system",
) -> EvalDataset:
    selected_traces: list[LLMTrace] = []
    for trace in getattr(ctx, "llm_traces", []) or []:
        if trace_ids is not None and trace.trace_id not in trace_ids:
            continue
        if trace_ids is None and not is_trace_backfill_eligible(trace):
            continue
        selected_traces.append(trace)

    eval_ids: list[str] = []
    for trace in selected_traces:
        eval_case = convert_trace_to_eval_case(ctx, trace_id=trace.trace_id)
        eval_ids.append(eval_case.eval_id)

    if not eval_ids:
        raise ValueError("No eligible failed/parser/safety traces are available for backfill.")

    dataset = create_dataset(
        ctx,
        name=name,
        description=description,
        case_ids=list(dict.fromkeys(eval_ids)),
        scenario_type="production_failure",
        source="production_trace",
        version=version,
        tags=[
            TRACE_BACKFILL_TAG,
            "parser",
            "safety",
            "regression",
            "gate_required",
            "v0.8-alpha.8",
        ],
        owner=owner,
        metadata={
            "source_trace_ids": [trace.trace_id for trace in selected_traces],
            "trace_backfill_policy_version": TRACE_BACKFILL_POLICY_VERSION,
        },
    )
    append_audit_event(
        ctx,
        actor="system",
        event_type="trace_backfill_dataset_created",
        target_type="eval_dataset",
        target_id=dataset.dataset_id,
        after=dataset,
        metadata={"trace_count": len(selected_traces), "case_count": len(dataset.case_ids)},
    )
    return dataset


def build_trace_backfill_summary(ctx: ProjectContext) -> dict[str, Any]:
    backfilled_cases = [
        case
        for case in getattr(ctx, "eval_cases", []) or []
        if getattr(case, "source_trace_id", None)
    ]
    datasets = [
        dataset
        for dataset in getattr(ctx, "eval_datasets", []) or []
        if dataset.source == TRACE_BACKFILL_TAG or TRACE_BACKFILL_TAG in (dataset.tags or [])
    ]
    trace_ids_with_eval_case = {
        case.source_trace_id for case in backfilled_cases if case.source_trace_id
    }
    eval_ids_in_trace_datasets = {
        eval_id for dataset in datasets for eval_id in (dataset.case_ids or [])
    }
    eligible_trace_ids = [
        trace.trace_id
        for trace in getattr(ctx, "llm_traces", []) or []
        if is_trace_backfill_eligible(trace)
    ]
    backfilled_eval_ids_without_trace_dataset = [
        case.eval_id for case in backfilled_cases if case.eval_id not in eval_ids_in_trace_datasets
    ]
    trace_ids_without_eval_case = [
        trace_id for trace_id in eligible_trace_ids if trace_id not in trace_ids_with_eval_case
    ]
    return {
        "policy_version": TRACE_BACKFILL_POLICY_VERSION,
        "runtime_validation": "deferred_by_instruction",
        "eligible_trace_count": len(eligible_trace_ids),
        "eligible_trace_ids": eligible_trace_ids,
        "backfilled_eval_case_count": len(backfilled_cases),
        "backfilled_eval_case_ids": [case.eval_id for case in backfilled_cases],
        "source_trace_ids": sorted(trace_ids_with_eval_case),
        "trace_backfill_dataset_ids": [dataset.dataset_id for dataset in datasets],
        "failed_trace_count": len(eligible_trace_ids),
        "failed_trace_ids_without_eval_case": trace_ids_without_eval_case,
        "eligible_trace_ids_without_eval_case": trace_ids_without_eval_case,
        "backfilled_eval_ids_without_trace_dataset": backfilled_eval_ids_without_trace_dataset,
        "gate_ready": not (
            trace_ids_without_eval_case or backfilled_eval_ids_without_trace_dataset
        ),
    }
