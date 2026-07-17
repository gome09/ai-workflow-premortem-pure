# core/eval_runner.py
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from core.audit_service import append_audit_event
from core.context_manager import get_llm_for_stage
from core.eval_judge import judge_eval_run
from core.eval_judgment_service import create_judgment_from_eval_run
from core.models import EvalCase, EvalRun, ProjectContext, WorkflowNode
from core.oversight_service import create_actions_from_eval_failures, current_stage_output_version

VALID_RUN_MODES = {"manual", "dry_run", "llm_node"}

# TODO: llm_node 模式下应该真正调用 LLM 来跑 eval，现在只是创建了 EvalRun 记录
# 没有真正执行。这个功能后面再补


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


def _build_node_eval_prompt(case: EvalCase, node: WorkflowNode) -> tuple[str, str]:
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
            case.input_payload,
            "",
            "# Expected behavior for later judging",
            case.expected_behavior,
            "",
            "# Pass criteria",
            "\n".join(f"- {criterion}" for criterion in case.pass_criteria) or "(none provided)",
        ]
    )
    return system_prompt, user_prompt


def _maybe_apply_llm_judge(ctx: ProjectContext, case: EvalCase, run: EvalRun) -> None:
    """T3.6：规则层 needs_review 时生成 LLM 建议；autofinal 仅对 LOW/MEDIUM 会话采纳。

    manual run 是人工评分外壳（无 actual_output），不生成建议；
    任何 judge 失败静默降级（建议为 None），绝不阻断 eval 主路径。
    """
    from core.config import settings

    if not settings.eval_llm_judge:
        return
    if run.run_mode == "manual" or run.judge_result != "needs_review":
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


def run_eval_case(
    ctx: ProjectContext,
    *,
    eval_id: str,
    run_mode: str = "manual",
    dataset_id: str | None = None,
    experiment_id: str | None = None,
    run_index: int | None = None,
) -> EvalRun:
    if run_mode not in VALID_RUN_MODES:
        raise ValueError(f"Unsupported eval run_mode: {run_mode}")

    case = _find_eval_case(ctx, eval_id)
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
            system_prompt, user_prompt = _build_node_eval_prompt(case, node)
            llm = get_llm_for_stage(3)
            response = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
            run.actual_output = str(response.content)

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
        run.error_message = str(exc)
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
        )
        for index, eval_id in enumerate(selected)
    ]
    create_actions_from_eval_failures(ctx, 3)
    return runs
