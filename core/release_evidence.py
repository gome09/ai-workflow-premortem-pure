# core/release_evidence.py
"""Release evidence selection and snapshotting.

This module is pure read-only domain logic:

- required high-risk EvalCases;
- one completed ``target_http`` EvalExperiment as the release batch;
- per-run execution and semantic validity;
- an append-only evidence snapshot digest consumed by ``ProjectApproval``.

It deliberately does not import ``core.approval_service`` to avoid a cycle.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.coverage.policy import required_high_risk_node_ids
from core.evaluation_version import eval_case_digest
from core.models import EvalCase, EvalExperiment, EvalRun, HumanCalibration, ProjectContext
from core.risk_treatment_service import high_risk_treatment_requirements


@dataclass(frozen=True)
class ReleaseBatch:
    experiment_id: str
    run_ids: tuple[str, ...]
    eval_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseEvidenceContext:
    required_cases: list[EvalCase]
    missing_node_ids: list[str]
    release_batch: ReleaseBatch | None
    valid_runs: list[EvalRun]
    blockers: list[dict[str, Any]]


def _blocker(
    code: str,
    message: str,
    *,
    severity: str = "high",
    source_type: str | None = None,
    source_id: str | None = None,
    required_resolution: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "severity": severity,
        "source_type": source_type,
        "source_id": source_id,
        "required_resolution": required_resolution,
    }


def _text_sha256(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _latest_human_calibration(ctx: ProjectContext, eval_run_id: str) -> HumanCalibration | None:
    matches = [
        calibration
        for calibration in getattr(ctx, "human_calibrations", []) or []
        if calibration.eval_run_id == eval_run_id
    ]
    return sorted(matches, key=lambda item: item.created_at)[-1] if matches else None


def required_release_cases(ctx: ProjectContext) -> tuple[list[EvalCase], list[str]]:
    """Return all Stage 3 EvalCases for required high-risk nodes plus gap node ids."""
    required_nodes = sorted(required_high_risk_node_ids(ctx))
    if not required_nodes:
        return [], []
    node_set = set(required_nodes)
    cases = sorted(
        [case for case in ctx.eval_cases if case.stage_id == 3 and case.target_node_id in node_set],
        key=lambda item: item.eval_id,
    )
    covered = {case.target_node_id for case in cases}
    missing = [node_id for node_id in required_nodes if node_id not in covered]
    return cases, missing


def _deployment_declared(ctx: ProjectContext) -> bool:
    deployment = ctx.target_deployment
    return bool(deployment is not None and deployment.endpoint and deployment.version)


def release_run_reasons(
    ctx: ProjectContext,
    run: EvalRun,
    case: EvalCase | None,
    *,
    evaluation_digest: str,
) -> list[str]:
    """Return deterministic reasons why a run is not valid release evidence."""
    deployment = ctx.target_deployment
    reasons: list[str] = []
    if run.run_mode != "target_http":
        reasons.append("run_mode")
    if run.execution_kind != "real_target_execution":
        reasons.append("execution_kind")
    if run.execution_outcome != "success":
        reasons.append("execution_outcome")
    if run.status != "completed":
        reasons.append("status")
    if run.truncated:
        # 字节/字符上限截断的响应不是完整输出，不能作为通过证据。
        reasons.append("output_truncated")
    if run.judge_result != "passed":
        reasons.append("judge_result")
    elif run.run_mode == "target_http":
        # 真实目标通过必须能追溯到人工复核与书面判定依据；
        # 仅写入 judge_result=passed 或缺少 actual_output 的运行不能作为上线证据。
        if not (run.actual_output or "").strip():
            reasons.append("actual_output_missing")
        calibration = _latest_human_calibration(ctx, run.run_id)
        if run.judge_mode != "human" or calibration is None or calibration.human_label != "passed":
            reasons.append("human_review_missing")
        elif (
            not (calibration.human_comment or "").strip()
            or not (calibration.reviewer_id or "").strip()
        ):
            reasons.append("human_review_basis_missing")
    if run.evaluation_version_digest != evaluation_digest:
        reasons.append("stale_evaluation_version")
    if case is None:
        reasons.append("missing_eval_case")
    elif run.case_version_digest != eval_case_digest(case):
        reasons.append("stale_case_version")
    if deployment is None or not deployment.endpoint or not deployment.version:
        reasons.append("target_deployment_missing")
    else:
        if run.target_endpoint != deployment.endpoint:
            reasons.append("target_endpoint_mismatch")
        if run.target_deployment_version != deployment.version:
            reasons.append("target_deployment_version_mismatch")
    return reasons


def _experiment_sort_key(experiment: EvalExperiment) -> tuple[datetime, str]:
    return (experiment.completed_at or experiment.created_at, experiment.experiment_id)


def _case_by_eval_id(ctx: ProjectContext) -> dict[str, EvalCase]:
    return {case.eval_id: case for case in ctx.eval_cases}


def _runs_for_experiment(ctx: ProjectContext, experiment: EvalExperiment) -> list[EvalRun]:
    run_ids = set(experiment.run_ids or [])
    return [run for run in ctx.eval_runs if run.run_id in run_ids]


@dataclass(frozen=True)
class _ExperimentEvaluation:
    runs: list[EvalRun]
    relevant: list[EvalRun]
    missing_eval_ids: list[str]
    invalid: list[tuple[EvalRun, list[str]]]
    valid_runs: list[EvalRun]
    covers_required: bool

    @property
    def hard_failures(self) -> list[tuple[EvalRun, list[str]]]:
        return [
            (run, reasons)
            for run, reasons in self.invalid
            if set(reasons).intersection(_HARD_FAILURE_REASONS)
        ]


_HARD_FAILURE_REASONS = frozenset(
    {
        "execution_outcome",
        "status",
        "judge_result",
        "output_truncated",
    }
)


def _release_batch_failed_blocker(experiment: EvalExperiment) -> dict[str, Any]:
    return _blocker(
        "release_batch_failed",
        f"评估批次 {experiment.experiment_id} 已失败；不能用更旧的通过批次掩盖该失败。",
        source_type="eval_experiment",
        source_id=experiment.experiment_id,
        required_resolution="run_eval_experiment",
    )


def _missing_case_blockers(
    cases_by_id: dict[str, EvalCase],
    experiment: EvalExperiment,
    missing_eval_ids: list[str],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for eval_id in missing_eval_ids:
        case = cases_by_id.get(eval_id)
        blocker = _blocker(
            "real_target_test",
            f"必测用例 {eval_id} 在评估批次 {experiment.experiment_id} 中没有运行记录。",
            source_type="eval_case",
            source_id=eval_id,
            required_resolution="run_eval_experiment",
        )
        if case is not None and case.target_node_id:
            blocker["source_type"] = "eval_node"
            blocker["source_id"] = case.target_node_id
        blockers.append(blocker)
    return blockers


def _invalid_run_blockers(
    invalid: list[tuple[EvalRun, list[str]]],
) -> list[dict[str, Any]]:
    return [
        _blocker(
            "real_target_test",
            (
                f"必测运行 {run.run_id}（用例 {run.eval_id}）不是有效的当前版本"
                f"真实目标通过证据：{', '.join(reasons) or 'unknown'}。"
            ),
            source_type="eval_run",
            source_id=run.run_id,
            required_resolution="run_eval_experiment",
        )
        for run, reasons in invalid
    ]


def _evaluate_experiment(
    ctx: ProjectContext,
    experiment: EvalExperiment,
    *,
    required_eval_ids: list[str],
    cases_by_id: dict[str, EvalCase],
    evaluation_digest: str,
) -> _ExperimentEvaluation:
    runs = _runs_for_experiment(ctx, experiment)
    required_set = set(required_eval_ids)
    relevant = [run for run in runs if not required_set or run.eval_id in required_set]
    declared_eval_ids = set(experiment.eval_ids or []) | {run.eval_id for run in runs}
    covers_required = required_set.issubset(declared_eval_ids)
    covered = {run.eval_id for run in relevant}
    missing = [eval_id for eval_id in required_eval_ids if eval_id not in covered]
    valid_runs: list[EvalRun] = []
    invalid: list[tuple[EvalRun, list[str]]] = []
    for run in relevant:
        reasons = release_run_reasons(
            ctx,
            run,
            cases_by_id.get(run.eval_id),
            evaluation_digest=evaluation_digest,
        )
        if reasons:
            invalid.append((run, reasons))
        else:
            valid_runs.append(run)
    return _ExperimentEvaluation(
        runs=runs,
        relevant=relevant,
        missing_eval_ids=missing,
        invalid=invalid,
        valid_runs=valid_runs,
        covers_required=covers_required,
    )


def _newer_hard_failure_blockers(
    ctx: ProjectContext,
    *,
    selected_run_ids: set[str],
    required_eval_ids: list[str],
    batch_time: datetime,
    cases_by_id: dict[str, EvalCase],
    evaluation_digest: str,
) -> list[dict[str, Any]]:
    """Block hard failures that appeared after the selected passing batch.

    A single failing rerun after approval must not be masked by the older
    complete batch, even when no new EvalExperiment was created.
    """
    required_set = set(required_eval_ids)
    newer: list[tuple[EvalRun, list[str]]] = []
    for run in ctx.eval_runs:
        if run.run_id in selected_run_ids:
            continue
        if required_set and run.eval_id not in required_set:
            continue
        run_time = run.completed_at or run.created_at
        if run_time <= batch_time:
            continue
        reasons = release_run_reasons(
            ctx,
            run,
            cases_by_id.get(run.eval_id),
            evaluation_digest=evaluation_digest,
        )
        if set(reasons).intersection(_HARD_FAILURE_REASONS):
            newer.append((run, reasons))
    return _invalid_run_blockers(newer)


def select_release_batch(
    ctx: ProjectContext,
    required_cases: list[EvalCase],
    *,
    evaluation_digest: str,
) -> tuple[ReleaseBatch | None, list[dict[str, Any]], list[EvalRun]]:
    """Select one current ``target_http`` experiment without falling back past failures.

    The gate must be monotonic with respect to batch execution time: a newer
    failed/incomplete batch must never be masked by an older passing batch.
    """
    cases_by_id = _case_by_eval_id(ctx)
    required_eval_ids = sorted({case.eval_id for case in required_cases})
    indexed_experiments = list(
        enumerate(
            experiment
            for experiment in ctx.eval_experiments
            if experiment.run_mode == "target_http" and experiment.status in {"completed", "failed"}
        )
    )
    # 同一时间戳下后追加的实验更新；列表顺序是确定性的最终 tie-breaker。
    indexed_experiments.sort(
        key=lambda item: (_experiment_sort_key(item[1]), item[0]),
        reverse=True,
    )
    experiments = [experiment for _, experiment in indexed_experiments]
    if not experiments:
        return (
            None,
            [
                _blocker(
                    "release_batch",
                    "没有已完成的 target_http 评估批次；上线证据必须来自同一评估批次。",
                    source_type="eval_experiment",
                    required_resolution="run_eval_experiment",
                )
            ],
            [],
        )

    if not required_eval_ids:
        for experiment in experiments:
            evaluation = _evaluate_experiment(
                ctx,
                experiment,
                required_eval_ids=[],
                cases_by_id=cases_by_id,
                evaluation_digest=evaluation_digest,
            )
            if experiment.status == "failed":
                return (
                    None,
                    [_release_batch_failed_blocker(experiment)],
                    [],
                )
            if not evaluation.runs:
                continue
            if not evaluation.invalid:
                selected_run_ids = {run.run_id for run in evaluation.valid_runs}
                newer_blockers = _newer_hard_failure_blockers(
                    ctx,
                    selected_run_ids=selected_run_ids,
                    required_eval_ids=[],
                    batch_time=_experiment_sort_key(experiment)[0],
                    cases_by_id=cases_by_id,
                    evaluation_digest=evaluation_digest,
                )
                if newer_blockers:
                    return None, newer_blockers, []
                return (
                    ReleaseBatch(
                        experiment_id=experiment.experiment_id,
                        run_ids=tuple(run.run_id for run in evaluation.valid_runs),
                        eval_ids=tuple(sorted({run.eval_id for run in evaluation.valid_runs})),
                    ),
                    [],
                    list(evaluation.valid_runs),
                )
            return None, _invalid_run_blockers(evaluation.invalid), []
        return (
            None,
            [
                _blocker(
                    "real_target_test",
                    "尚无当前评估版本的通过真实目标测试，不能获得上线批准。",
                    source_type="eval_run",
                    required_resolution="run_eval_experiment",
                )
            ],
            [],
        )

    best_blockers: list[dict[str, Any]] = []
    for experiment in experiments:
        evaluation = _evaluate_experiment(
            ctx,
            experiment,
            required_eval_ids=required_eval_ids,
            cases_by_id=cases_by_id,
            evaluation_digest=evaluation_digest,
        )

        if experiment.status == "failed":
            if evaluation.covers_required or evaluation.relevant:
                return (
                    None,
                    [_release_batch_failed_blocker(experiment)]
                    + _missing_case_blockers(cases_by_id, experiment, evaluation.missing_eval_ids)
                    + _invalid_run_blockers(evaluation.invalid),
                    [],
                )
            continue

        if evaluation.covers_required:
            if not evaluation.missing_eval_ids and not evaluation.invalid and evaluation.runs:
                selected_run_ids = {run.run_id for run in evaluation.valid_runs}
                newer_blockers = _newer_hard_failure_blockers(
                    ctx,
                    selected_run_ids=selected_run_ids,
                    required_eval_ids=required_eval_ids,
                    batch_time=_experiment_sort_key(experiment)[0],
                    cases_by_id=cases_by_id,
                    evaluation_digest=evaluation_digest,
                )
                if newer_blockers:
                    return None, newer_blockers, []
                return (
                    ReleaseBatch(
                        experiment_id=experiment.experiment_id,
                        run_ids=tuple(run.run_id for run in evaluation.valid_runs),
                        eval_ids=tuple(required_eval_ids),
                    ),
                    [],
                    list(evaluation.valid_runs),
                )
            return (
                None,
                _missing_case_blockers(cases_by_id, experiment, evaluation.missing_eval_ids)
                + _invalid_run_blockers(evaluation.invalid),
                [],
            )

        hard_failures = evaluation.hard_failures
        if hard_failures:
            return None, _invalid_run_blockers(hard_failures), []

        if not best_blockers and evaluation.relevant:
            best_blockers = _missing_case_blockers(
                cases_by_id, experiment, evaluation.missing_eval_ids
            ) + _invalid_run_blockers(evaluation.invalid)

    if not best_blockers:
        best_blockers = [
            _blocker(
                "real_target_test",
                "没有覆盖全部必测项且全部通过的已完成 target_http 评估批次。",
                source_type="eval_experiment",
                required_resolution="run_eval_experiment",
            )
        ]
    return None, best_blockers, []


def _latest_treatment(ctx: ProjectContext, source_type: str, source_id: str):
    matches = [
        treatment
        for treatment in ctx.risk_treatments
        if treatment.source_type == source_type and treatment.source_id == source_id
    ]
    return sorted(matches, key=lambda item: item.updated_at)[-1] if matches else None


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def release_evidence_snapshot(
    ctx: ProjectContext,
    *,
    batch_run_ids: Sequence[str],
    required_eval_ids: Sequence[str],
    evaluation_digest: str,
) -> dict[str, Any]:
    """Stable snapshot of the evidence that must remain unchanged for an approval."""
    run_ids = sorted({run_id for run_id in batch_run_ids})
    batch_runs = [run for run in ctx.eval_runs if run.run_id in set(run_ids)]
    batch_runs.sort(key=lambda run: run.run_id)
    calibrations = []
    for calibration in sorted(ctx.human_calibrations, key=lambda item: item.calibration_id):
        if calibration.eval_run_id in set(run_ids):
            calibrations.append(
                {
                    "calibration_id": calibration.calibration_id,
                    "eval_run_id": calibration.eval_run_id,
                    "human_label": calibration.human_label,
                    "reviewer_id": calibration.reviewer_id,
                    "human_comment_sha256": _text_sha256(calibration.human_comment),
                    "disagreement_reason_sha256": _text_sha256(calibration.disagreement_reason),
                    "created_at": _iso(calibration.created_at),
                }
            )
    treatments = []
    for requirement in high_risk_treatment_requirements(ctx):
        treatment = _latest_treatment(ctx, requirement.source_type, requirement.source_id)
        treatments.append(
            {
                "source_type": requirement.source_type,
                "source_id": requirement.source_id,
                "treatment_id": treatment.treatment_id if treatment else "",
                "owner": treatment.owner if treatment else "",
                "mitigation_plan": treatment.mitigation_plan if treatment else "",
                "status": treatment.status if treatment else "",
                "reviewed_by": treatment.reviewed_by if treatment else "",
                "reviewed_at": _iso(treatment.reviewed_at) if treatment else "",
                "review_note": treatment.review_note if treatment else "",
                "evaluation_version_digest": (
                    treatment.evaluation_version_digest if treatment else ""
                ),
            }
        )
    safety = [
        {
            "finding_id": finding.finding_id,
            "severity": finding.severity,
            "status": finding.status,
        }
        for finding in sorted(ctx.safety_findings, key=lambda item: item.finding_id)
        if finding.severity in {"high", "critical"}
    ]
    actions = [
        {
            "action_id": action.action_id,
            "status": action.status,
            "blocking": action.blocking,
            "stage_id": action.stage_id,
            "stage_output_version": action.stage_output_version,
        }
        for action in sorted(ctx.pending_actions, key=lambda item: item.action_id)
        if action.blocking
    ]
    return {
        "evaluation_digest": evaluation_digest,
        "required_eval_ids": sorted(required_eval_ids),
        "release_batch_run_ids": run_ids,
        "batch_runs": [
            {
                "run_id": run.run_id,
                "eval_id": run.eval_id,
                "status": run.status,
                "execution_outcome": run.execution_outcome,
                "judge_result": run.judge_result,
                "judge_mode": run.judge_mode,
                "judge_reason_sha256": _text_sha256(run.judge_reason),
                "actual_output_sha256": _text_sha256(run.actual_output),
                "actual_output_length": len(run.actual_output or ""),
                "evaluation_version_digest": run.evaluation_version_digest,
                "case_version_digest": run.case_version_digest,
                "target_endpoint": run.target_endpoint,
                "target_deployment_version": run.target_deployment_version,
                "completed_at": _iso(run.completed_at),
            }
            for run in batch_runs
        ],
        "calibrations": calibrations,
        "treatments": treatments,
        "safety_findings": safety,
        "blocking_actions": actions,
    }


def release_evidence_digest(
    ctx: ProjectContext,
    *,
    batch_run_ids: Sequence[str],
    required_eval_ids: Sequence[str],
    evaluation_digest: str,
) -> str:
    snapshot = release_evidence_snapshot(
        ctx,
        batch_run_ids=batch_run_ids,
        required_eval_ids=required_eval_ids,
        evaluation_digest=evaluation_digest,
    )
    encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_release_evidence(
    ctx: ProjectContext,
    *,
    evaluation_digest: str,
) -> ReleaseEvidenceContext:
    """Convenience bundle used by approval readiness and tests."""
    required_cases, missing_nodes = required_release_cases(ctx)
    batch, blockers, valid_runs = select_release_batch(
        ctx, required_cases, evaluation_digest=evaluation_digest
    )
    if missing_nodes:
        blockers = [
            _blocker(
                "required_test_case",
                f"高风险节点 {node_id} 没有 Stage 3 EvalCase，无法定义必测集合。",
                source_type="eval_node",
                source_id=node_id,
                required_resolution="sync_eval_cases",
            )
            for node_id in missing_nodes
        ] + blockers
    if not _deployment_declared(ctx):
        blockers = [
            _blocker(
                "target_deployment",
                "尚未声明目标部署 endpoint/version，不能把真实目标运行作为上线证据。",
                source_type="target_deployment",
                required_resolution="declare_target_deployment",
            )
        ] + blockers
    return ReleaseEvidenceContext(
        required_cases=required_cases,
        missing_node_ids=missing_nodes,
        release_batch=batch,
        valid_runs=valid_runs,
        blockers=blockers,
    )
