# core/eval_runner.py
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from core.audit_service import append_audit_event
from core.config import settings
from core.context_manager import get_llm_for_stage
from core.eval_judge import judge_eval_run
from core.eval_judgment_service import create_judgment_from_eval_run
from core.evaluation_version import current_evaluation_digest, eval_case_digest
from core.llm.errors import record_llm_failure, summarize_llm_error
from core.llm.outbound_guard import guarded_invoke
from core.models import EvalCase, EvalRun, ProjectContext, WorkflowNode
from core.oversight_service import create_actions_from_eval_failures, current_stage_output_version
from core.target_testing import (
    HttpJsonTargetAdapter,
    TargetSystemConfig,
    TargetTestResponse,
    sanitize_endpoint,
)

logger = logging.getLogger(__name__)

VALID_RUN_MODES = {"manual", "dry_run", "llm_node", "target_http"}

_EXECUTION_KINDS = {
    "manual": "manual_simulation",
    "dry_run": "dry_run_simulation",
    "target_http": "real_target_execution",
}


def _execution_kind(run_mode: str) -> str:
    if run_mode == "llm_node":
        return "mock_model_execution" if settings.llm_mode == "mock" else "platform_model_execution"
    return _EXECUTION_KINDS.get(run_mode, "unknown")


def _find_eval_case(ctx: ProjectContext, eval_id: str) -> EvalCase:
    for case in ctx.eval_cases:
        if case.eval_id == eval_id:
            return case
    raise ValueError(f"Eval case not found: {eval_id}")


def _find_target_node(ctx: ProjectContext, node_id: str | None) -> WorkflowNode | None:
    if not node_id or not ctx.stage_2_output:
        return None
    for node in ctx.stage_2_output.workflow_nodes:
        if node.node_id == node_id:
            return node
    return None


def _build_candidate_prompt(node: WorkflowNode, input_payload: str) -> tuple[str, str]:
    """Build the prompt sent to the model under test.

    Oracle fields (``expected_behavior`` / ``pass_criteria``) must never enter
    this prompt. They are only consumed by the judge path after the candidate
    output exists, which keeps the evaluator and the evaluated system separated.
    """
    system_prompt = (
        "You are executing one deterministic workflow node for an eval case. "
        "Follow the node prompt template and do not decide the whole workflow."
    )
    user_prompt = "\n".join(
        [
            "# Workflow node prompt template",
            node.prompt_template or "(missing prompt template)",
            "",
            "# Eval input payload",
            input_payload,
        ]
    )
    return system_prompt, user_prompt


def _maybe_apply_llm_judge(ctx: ProjectContext, case: EvalCase, run: EvalRun) -> None:
    """T3.6：规则层 needs_review 时生成 LLM 建议；autofinal 仅对 LOW/MEDIUM 会话采纳。

    manual run 是人工评分外壳（无 actual_output），不生成建议；
    任何 judge 失败静默降级（建议为 None），绝不阻断 eval 主路径。
    """
    if not settings.eval_llm_judge:
        return
    if run.run_mode in {"manual", "target_http"} or run.judge_result != "needs_review":
        return

    from core.eval_llm_judge import generate_llm_judge_suggestion
    from core.gates.risk_profile import ProjectGateRiskTier, classify_project_risk

    suggestion = generate_llm_judge_suggestion(ctx, case, run)
    run.llm_judge_suggestion = suggestion
    if suggestion is None:
        return

    tier, _ = classify_project_risk(ctx)
    if tier in (ProjectGateRiskTier.HIGH, ProjectGateRiskTier.CRITICAL):
        return  # HIGH/CRITICAL 永远保持 needs_review 待人工
    if settings.eval_llm_judge_autofinal:
        run.judge_result = suggestion["suggested_result"]
        run.judge_mode = "llm"
        run.judge_reason = (
            f"LLM judge (autofinal, confidence={suggestion['confidence']:.2f}): "
            f"{suggestion['rationale']}"
        )


def _execute_target(
    ctx: ProjectContext,
    case: EvalCase,
    target_config: TargetSystemConfig,
) -> TargetTestResponse:
    """Run one eval input against the real HTTP JSON target."""
    adapter = HttpJsonTargetAdapter(target_config)
    return adapter.execute(
        case.input_payload,
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        node_id=case.target_node_id,
        classification=ctx.data_classification,
    )


def run_eval_case(
    ctx: ProjectContext,
    *,
    eval_id: str,
    run_mode: str = "manual",
    dataset_id: str | None = None,
    experiment_id: str | None = None,
    run_index: int | None = None,
    target_config: TargetSystemConfig | None = None,
) -> EvalRun:
    if run_mode not in VALID_RUN_MODES:
        raise ValueError(f"Unsupported eval run_mode: {run_mode}")
    if run_mode == "target_http" and target_config is None:
        raise ValueError("target_config is required for target_http eval runs")

    target_endpoint = ""
    if target_config is not None:
        try:
            target_endpoint = sanitize_endpoint(target_config.endpoint)
        except ValueError as exc:
            raise ValueError(f"Invalid target_config endpoint: {exc}") from exc

    case = _find_eval_case(ctx, eval_id)
    deployment = ctx.target_deployment
    if (
        run_mode == "target_http"
        and deployment is not None
        and deployment.endpoint
        and target_endpoint != deployment.endpoint
    ):
        raise ValueError(
            f"Target endpoint does not match the declared target deployment ({deployment.endpoint})"
        )
    target_deployment_version = (
        deployment.version if run_mode == "target_http" and deployment is not None else ""
    )
    before_count = len(ctx.eval_runs)
    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        dataset_id=dataset_id,
        experiment_id=experiment_id,
        run_index=run_index,
        target_node_id=case.target_node_id,
        covered_failure_mode_ids=list(case.covered_failure_mode_ids or []),
        stage_output_version=current_stage_output_version(ctx, 3),
        run_mode=run_mode,  # type: ignore[arg-type]
        execution_kind=_execution_kind(run_mode),  # type: ignore[arg-type]
        evaluation_version_digest=current_evaluation_digest(ctx),
        target_endpoint=target_endpoint,
        target_deployment_version=target_deployment_version,
        case_version_digest=eval_case_digest(case),
        input_payload=case.input_payload,
        expected_behavior=case.expected_behavior,
        pass_criteria=list(case.pass_criteria or []),
    )
    ctx.eval_runs.append(run)
    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_run_created",
        target_type="eval_run",
        target_id=run.run_id,
        after=run,
        metadata={
            "eval_id": case.eval_id,
            "run_mode": run_mode,
            "execution_kind": run.execution_kind,
            "evaluation_version_digest": run.evaluation_version_digest,
            "case_version_digest": run.case_version_digest,
            "target_endpoint": run.target_endpoint,
            "target_deployment_version": run.target_deployment_version,
            "oracle_fields_included": False,
            "stage_output_version": run.stage_output_version,
            "pass_criteria_count": len(run.pass_criteria or []),
        },
    )

    if run_mode == "manual":
        # Manual mode creates an auditable run shell. The reviewer can later score
        # the EvalCase or fill actual_output through the score endpoint.
        before = run.model_dump(mode="json")
        judge_eval_run(case, run)
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        create_judgment_from_eval_run(ctx, run)
        append_audit_event(
            ctx,
            actor="system",
            event_type="eval_run_judged",
            target_type="eval_run",
            target_id=run.run_id,
            before=before,
            after=run,
            metadata={
                "eval_id": case.eval_id,
                "judge_mode": run.judge_mode,
                "status": run.status,
                "judge_result": run.judge_result,
            },
        )
        return run

    before = run.model_dump(mode="json")
    run.status = "running"
    try:
        if run_mode == "dry_run":
            run.actual_output = (
                "DRY_RUN: no model call was made. Use this run to validate eval plumbing."
            )
        elif run_mode == "llm_node":
            node = _find_target_node(ctx, case.target_node_id)
            if node is None:
                raise ValueError(f"Workflow node not found for eval case: {case.target_node_id}")
            system_prompt, user_prompt = _build_candidate_prompt(node, case.input_payload)
            llm = get_llm_for_stage(3)
            response = guarded_invoke(
                llm,
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
                ctx=ctx,
                stage=3,
            )
            run.actual_output = str(response.content)
        elif run_mode == "target_http":
            if target_config is None:
                raise ValueError("target_config is required for target_http eval runs")
            target_response = _execute_target(ctx, case, target_config)
            run.execution_outcome = target_response.outcome
            run.latency_ms = target_response.latency_ms
            run.target_endpoint = target_response.endpoint or target_endpoint
            if target_response.outcome == "success":
                run.actual_output = target_response.output
            else:
                run.actual_output = ""
                run.error_message = (
                    f"{target_response.error_code}: {target_response.error_message}"
                ).strip(": ")
                if target_response.outcome in {"timeout", "error"}:
                    run.status = "failed"
                    run.completed_at = datetime.utcnow()

            logger.info(
                "target_execution_finished",
                extra={
                    "event": "target_execution_finished",
                    "session_id": ctx.session_id,
                    "run_id": run.run_id,
                    "eval_id": case.eval_id,
                    "outcome": target_response.outcome,
                    "status_code": target_response.status_code,
                    "latency_ms": target_response.latency_ms,
                    "error_code": target_response.error_code,
                    "endpoint": target_response.endpoint or target_endpoint,
                },
            )
            try:
                from api.metrics import record_target_execution

                record_target_execution(target_response.outcome)
            except Exception:  # pragma: no cover - metrics must never break eval runs
                logger.debug("record_target_execution failed; non-fatal", exc_info=True)

        if run.status != "failed":
            judge_eval_run(case, run)
            _maybe_apply_llm_judge(ctx, case, run)
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            create_judgment_from_eval_run(
                ctx,
                run,
                metadata=(
                    {"llm_judge_suggestion": run.llm_judge_suggestion}
                    if run.llm_judge_suggestion
                    else None
                ),
            )
    except Exception as exc:  # noqa: BLE001 - failed eval runs must be auditable
        run.status = "failed"
        error_code = "eval_execution_error"
        if run_mode == "llm_node":
            error_code, _retryable = record_llm_failure(
                exc,
                stage=3,
                session_id=ctx.session_id,
                logger=logger,
                event="eval_run_failed",
                extra_fields={
                    "run_id": run.run_id,
                    "eval_id": case.eval_id,
                    "run_mode": run_mode,
                },
            )
            run.error_message = summarize_llm_error(exc)
        else:
            run.error_message = str(exc)
            logger.warning(
                "eval_run_failed",
                extra={
                    "event": "eval_run_failed",
                    "session_id": ctx.session_id,
                    "run_id": run.run_id,
                    "eval_id": case.eval_id,
                    "run_mode": run_mode,
                    "error_code": error_code,
                    "error_type": type(exc).__name__,
                },
            )
        run.completed_at = datetime.utcnow()

    append_audit_event(
        ctx,
        actor="system",
        event_type="eval_run_completed",
        target_type="eval_run",
        target_id=run.run_id,
        before=before,
        after=run,
        metadata={
            "eval_id": case.eval_id,
            "run_mode": run_mode,
            "execution_kind": run.execution_kind,
            "execution_outcome": run.execution_outcome,
            "evaluation_version_digest": run.evaluation_version_digest,
            "case_version_digest": run.case_version_digest,
            "target_endpoint": run.target_endpoint,
            "target_deployment_version": run.target_deployment_version,
            "oracle_fields_included": False,
            "status": run.status,
            "judge_result": run.judge_result,
            "judge_mode": run.judge_mode,
            "violated_criteria": run.violated_criteria,
            "created_run_index": before_count,
        },
    )
    create_actions_from_eval_failures(ctx, 3, stage_output_version=run.stage_output_version)
    return run


def run_eval_cases(
    ctx: ProjectContext,
    *,
    eval_ids: Iterable[str] | None = None,
    run_mode: str = "manual",
    dataset_id: str | None = None,
    experiment_id: str | None = None,
    target_config: TargetSystemConfig | None = None,
) -> list[EvalRun]:
    selected = list(eval_ids) if eval_ids else [case.eval_id for case in ctx.eval_cases]
    if not selected:
        return []
    runs = [
        run_eval_case(
            ctx,
            eval_id=eval_id,
            run_mode=run_mode,
            dataset_id=dataset_id,
            experiment_id=experiment_id,
            run_index=index,
            target_config=target_config,
        )
        for index, eval_id in enumerate(selected)
    ]
    create_actions_from_eval_failures(ctx, 3)
    return runs
