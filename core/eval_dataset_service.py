# core/eval_dataset_service.py
from __future__ import annotations

from datetime import datetime

from core.audit_service import append_audit_event
from core.models import EvalDataset, ProjectContext
from core.traces import append_llm_trace, create_llm_trace


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([value for value in values if value]))


def _case_id_set(ctx: ProjectContext) -> set[str]:
    return {case.eval_id for case in ctx.eval_cases}


def _get_dataset(ctx: ProjectContext, dataset_id: str) -> EvalDataset:
    for dataset in ctx.eval_datasets:
        if dataset.dataset_id == dataset_id:
            return dataset
    raise ValueError(f"Eval dataset not found: {dataset_id}")


def _trace_dataset_event(ctx: ProjectContext, dataset: EvalDataset, event_kind: str) -> None:
    trace = create_llm_trace(
        ctx,
        stage=dataset.stage,
        node_name=event_kind,
        trace_type="eval",
        parser_status="not_applicable",
        metadata={
            "event_kind": event_kind,
            "dataset_id": dataset.dataset_id,
            "case_count": len(dataset.case_ids),
            "source": dataset.source,
            "version": dataset.version,
            "runtime_validation": "deferred_by_instruction",
        },
    )
    append_llm_trace(ctx, trace)


def list_datasets(ctx: ProjectContext) -> list[EvalDataset]:
    return list(ctx.eval_datasets)


def get_dataset(ctx: ProjectContext, dataset_id: str) -> EvalDataset:
    return _get_dataset(ctx, dataset_id)


def create_dataset(
    ctx: ProjectContext,
    *,
    name: str,
    description: str = "",
    case_ids: list[str] | None = None,
    scenario_type: str = "mixed",
    source: str = "manual",
    version: str = "0.1",
    tags: list[str] | None = None,
    owner: str = "system",
    metadata: dict | None = None,
) -> EvalDataset:
    valid_ids = _case_id_set(ctx)
    selected = _dedupe(case_ids or [])
    missing = [eval_id for eval_id in selected if eval_id not in valid_ids]
    if missing:
        raise ValueError(f"EvalCase not found for dataset: {missing}")

    dataset = EvalDataset(
        session_id=ctx.session_id,
        name=name,
        description=description,
        case_ids=selected,
        scenario_type=scenario_type,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        version=version,
        tags=tags or [],
        owner=owner,
        metadata={
            "runtime_validation": "deferred_by_instruction",
            "created_from": source,
            **(metadata or {}),
        },
    )
    ctx.eval_datasets.append(dataset)
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_dataset_created",
        target_type="eval_dataset",
        target_id=dataset.dataset_id,
        after=dataset,
        metadata={"case_count": len(dataset.case_ids), "source": dataset.source},
    )
    _trace_dataset_event(ctx, dataset, "eval_dataset_created")
    return dataset


def create_dataset_from_stage3(
    ctx: ProjectContext,
    *,
    name: str,
    description: str = "",
    version: str = "0.1",
    owner: str = "system",
    metadata: dict | None = None,
) -> EvalDataset:
    case_ids = [case.eval_id for case in ctx.eval_cases if case.stage_id == 3]
    return create_dataset(
        ctx,
        name=name,
        description=description,
        case_ids=case_ids,
        scenario_type="mixed",
        source="stage3_generated",
        version=version,
        owner=owner,
        tags=["stage3"],
    )


def add_cases_to_dataset(
    ctx: ProjectContext, *, dataset_id: str, eval_ids: list[str]
) -> EvalDataset:
    dataset = _get_dataset(ctx, dataset_id)
    valid_ids = _case_id_set(ctx)
    selected = _dedupe(eval_ids)
    missing = [eval_id for eval_id in selected if eval_id not in valid_ids]
    if missing:
        raise ValueError(f"EvalCase not found for dataset: {missing}")
    before = dataset.model_copy(deep=True)
    dataset.case_ids = _dedupe(dataset.case_ids + selected)
    dataset.updated_at = datetime.utcnow()
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_dataset_case_added",
        target_type="eval_dataset",
        target_id=dataset.dataset_id,
        before=before,
        after=dataset,
        metadata={"added_eval_ids": selected, "case_count": len(dataset.case_ids)},
    )
    _trace_dataset_event(ctx, dataset, "eval_dataset_case_added")
    return dataset


def remove_cases_from_dataset(
    ctx: ProjectContext, *, dataset_id: str, eval_ids: list[str]
) -> EvalDataset:
    dataset = _get_dataset(ctx, dataset_id)
    remove_set = set(eval_ids)
    before = dataset.model_copy(deep=True)
    dataset.case_ids = [eval_id for eval_id in dataset.case_ids if eval_id not in remove_set]
    dataset.updated_at = datetime.utcnow()
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_dataset_case_removed",
        target_type="eval_dataset",
        target_id=dataset.dataset_id,
        before=before,
        after=dataset,
        metadata={"removed_eval_ids": list(remove_set), "case_count": len(dataset.case_ids)},
    )
    _trace_dataset_event(ctx, dataset, "eval_dataset_case_removed")
    return dataset


def set_dataset_baseline(
    ctx: ProjectContext,
    *,
    dataset_id: str,
    baseline_experiment_id: str | None,
) -> EvalDataset:
    dataset = _get_dataset(ctx, dataset_id)
    if baseline_experiment_id is not None:
        experiment_ids = {experiment.experiment_id for experiment in ctx.eval_experiments}
        if baseline_experiment_id not in experiment_ids:
            raise ValueError(f"Eval experiment not found: {baseline_experiment_id}")
    before = dataset.model_copy(deep=True)
    dataset.baseline_experiment_id = baseline_experiment_id
    dataset.updated_at = datetime.utcnow()
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_dataset_updated",
        target_type="eval_dataset",
        target_id=dataset.dataset_id,
        before=before,
        after=dataset,
        metadata={"baseline_experiment_id": baseline_experiment_id},
    )
    _trace_dataset_event(ctx, dataset, "eval_dataset_updated")
    return dataset
