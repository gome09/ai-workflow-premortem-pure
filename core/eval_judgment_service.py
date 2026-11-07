from __future__ import annotations

import hashlib
import logging
from typing import Any, Literal

from core.audit_service import append_audit_event
from core.models import EvalJudgment, EvalRun, HumanActionStatus, HumanCalibration, ProjectContext
from core.version import APP_VERSION

JudgeLabel = Literal["passed", "failed", "needs_review"]

logger = logging.getLogger(__name__)


def _text_sha256(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _find_run(ctx: ProjectContext, eval_run_id: str) -> EvalRun:
    for run in getattr(ctx, "eval_runs", []) or []:
        if run.run_id == eval_run_id:
            return run
    raise ValueError(f"EvalRun not found: {eval_run_id}")


def _latest_judgment(ctx: ProjectContext, eval_run_id: str) -> EvalJudgment | None:
    matches = [j for j in getattr(ctx, "eval_judgments", []) or [] if j.eval_run_id == eval_run_id]
    return sorted(matches, key=lambda item: item.created_at, reverse=True)[0] if matches else None


def _score_for_label(label: str | None) -> float | None:
    if label == "passed":
        return 1.0
    if label == "failed":
        return 0.0
    if label == "needs_review":
        return 0.5
    return None


def list_eval_judgments(
    ctx: ProjectContext,
    *,
    eval_run_id: str | None = None,
    experiment_id: str | None = None,
) -> list[EvalJudgment]:
    judgments = list(getattr(ctx, "eval_judgments", []) or [])
    if eval_run_id:
        judgments = [item for item in judgments if item.eval_run_id == eval_run_id]
    if experiment_id:
        judgments = [item for item in judgments if item.experiment_id == experiment_id]
    return judgments


def list_human_calibrations(
    ctx: ProjectContext,
    *,
    eval_run_id: str | None = None,
    experiment_id: str | None = None,
) -> list[HumanCalibration]:
    calibrations = list(getattr(ctx, "human_calibrations", []) or [])
    if eval_run_id:
        calibrations = [item for item in calibrations if item.eval_run_id == eval_run_id]
    if experiment_id:
        calibrations = [item for item in calibrations if item.experiment_id == experiment_id]
    return calibrations


def create_judgment_from_eval_run(
    ctx: ProjectContext,
    run: EvalRun,
    *,
    judge_type: Literal["rule", "llm", "human_proxy"] | None = None,
    judge_model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> EvalJudgment:
    """Record the current EvalRun judge result as an auditable recommendation."""
    label: JudgeLabel = run.judge_result or "needs_review"
    inferred_type: Literal["rule", "llm", "human_proxy"] = (
        "llm" if run.judge_mode == "llm" else "rule"
    )
    if run.judge_mode == "human":
        inferred_type = "human_proxy"
    judgment = EvalJudgment(
        session_id=ctx.session_id,
        eval_run_id=run.run_id,
        eval_id=run.eval_id,
        experiment_id=run.experiment_id,
        judge_type=judge_type or inferred_type,
        judge_model=judge_model or run.run_mode,
        score=_score_for_label(label),
        label=label,
        rationale=run.judge_reason,
        uncertainty=0.5 if label == "needs_review" else 0.2,
        cited_rules=list(run.violated_criteria or []),
        metadata={
            "run_mode": run.run_mode,
            "judge_mode": run.judge_mode,
            "runtime_validation": "deferred_by_instruction",
            **(metadata or {}),
        },
    )
    ctx.eval_judgments.append(judgment)
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_judgment_created",
        target_type="eval_judgment",
        target_id=judgment.judgment_id,
        after=judgment,
        metadata={"eval_run_id": run.run_id, "judge_type": judgment.judge_type},
    )
    return judgment


def _resolve_eval_run_action(
    ctx: ProjectContext,
    run: EvalRun,
    *,
    human_label: JudgeLabel,
    reviewer: str,
    human_comment: str,
    actor_role: str,
    calibration_id: str,
) -> None:
    """Close the pending eval_run action with the human review decision.

    The human calibration *is* the review of that run. Leaving the action
    pending would permanently block release approval for high-risk nodes.
    """
    if human_label not in {"passed", "failed"}:
        return
    decision = "approve" if human_label == "passed" else "reject"
    from core.governance.action_resolution import resolve_action

    for action in list(ctx.pending_actions):
        if (
            action.source_type != "eval_run"
            or action.source_id != run.run_id
            or action.status != HumanActionStatus.PENDING.value
        ):
            continue
        if human_label == "failed" and action.action_type == "escalate":
            # critical 风险必须显式升级处理，不能由 failed 判定直接关闭。
            continue
        try:
            resolve_action(
                ctx,
                action_id=action.action_id,
                decision=decision,
                note=human_comment or f"EvalRun {run.run_id} calibrated to {human_label}.",
                idempotency_key=f"calibration:{calibration_id}",
                actor_id=reviewer,
                actor_role=actor_role,
            )
        except Exception:  # noqa: BLE001 - calibration audit must still succeed
            logger.warning(
                "Failed to close eval_run action %s after calibration %s",
                action.action_id,
                calibration_id,
                exc_info=True,
            )


def calibrate_eval_run(
    ctx: ProjectContext,
    *,
    eval_run_id: str,
    human_label: JudgeLabel,
    human_comment: str = "",
    reviewer_id: str = "human_reviewer",
    actor_role: str = "",
    disagreement_reason: str = "",
) -> HumanCalibration:
    run = _find_run(ctx, eval_run_id)
    reviewer = (reviewer_id or "").strip()
    if not reviewer:
        raise ValueError("Reviewer identity is required")
    if (
        run.run_mode == "target_http"
        and run.execution_outcome != "success"
        and human_label == "passed"
    ):
        raise ValueError(
            "A failed real-target execution cannot be calibrated to passed; "
            "rerun the target before claiming a passing result"
        )
    if human_label == "passed" and run.run_mode == "target_http":
        if run.status != "completed":
            raise ValueError(
                "A real-target run must be completed before it can be calibrated to passed"
            )
        if not (run.actual_output or "").strip():
            raise ValueError("A real-target run with empty output cannot be calibrated to passed")
        if not (human_comment or "").strip():
            raise ValueError(
                "Human pass calibration requires a written judgment basis (human_comment)"
            )
    latest = _latest_judgment(ctx, eval_run_id)
    before = run.model_copy(deep=True)
    judge_label = latest.label if latest else run.judge_result
    agreement = (judge_label == human_label) if judge_label else None
    calibration = HumanCalibration(
        session_id=ctx.session_id,
        eval_run_id=run.run_id,
        eval_id=run.eval_id,
        experiment_id=run.experiment_id,
        human_label=human_label,
        human_comment=human_comment,
        judge_label=judge_label,
        agreement=agreement,
        disagreement_reason=disagreement_reason,
        reviewer_id=reviewer,
        metadata={
            "runtime_validation": "deferred_by_instruction",
            "run_mode": run.run_mode,
            "execution_outcome": run.execution_outcome,
            "actual_output_sha256": _text_sha256(run.actual_output),
            "actual_output_length": len(run.actual_output or ""),
            "pass_criteria": list(run.pass_criteria or []),
            "target_endpoint": run.target_endpoint,
            "target_deployment_version": run.target_deployment_version,
            "evaluation_version_digest": run.evaluation_version_digest,
            "case_version_digest": run.case_version_digest,
        },
    )
    ctx.human_calibrations.append(calibration)

    run.judge_mode = "human"
    run.judge_result = human_label
    run.judge_reason = human_comment or f"Human calibration set final label to {human_label}."
    if human_label == "passed":
        run.violated_criteria = []

    _resolve_eval_run_action(
        ctx,
        run,
        human_label=human_label,
        reviewer=reviewer,
        human_comment=human_comment,
        actor_role=actor_role,
        calibration_id=calibration.calibration_id,
    )

    append_audit_event(
        ctx,
        actor="user",
        event_type="eval_run_human_calibrated",
        target_type="eval_run",
        target_id=run.run_id,
        before=before,
        after=run,
        metadata=calibration.model_dump(mode="json"),
    )
    return calibration


def build_eval_judgment_summary(ctx: ProjectContext) -> dict[str, Any]:
    judgments = list(getattr(ctx, "eval_judgments", []) or [])
    calibrations = list(getattr(ctx, "human_calibrations", []) or [])
    label_counts: dict[str, int] = {}
    judge_type_counts: dict[str, int] = {}
    for judgment in judgments:
        label_counts[judgment.label] = label_counts.get(judgment.label, 0) + 1
        judge_type_counts[judgment.judge_type] = judge_type_counts.get(judgment.judge_type, 0) + 1

    calibrated = [item for item in calibrations if item.agreement is not None]
    disagreements = [item for item in calibrated if item.agreement is False]
    agreement_rate = None
    if calibrated:
        agreement_rate = (len(calibrated) - len(disagreements)) / len(calibrated)

    return {
        "policy_version": APP_VERSION,
        "runtime_validation": "deferred_by_instruction",
        "judgment_count": len(judgments),
        "judge_type_counts": judge_type_counts,
        "label_counts": label_counts,
        "human_calibration_count": len(calibrations),
        "human_disagreement_count": len(disagreements),
        "judge_human_agreement_rate": agreement_rate,
        "disagreement_eval_run_ids": [item.eval_run_id for item in disagreements],
    }
