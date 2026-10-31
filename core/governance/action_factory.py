# core/governance/action_factory.py
"""Creation of PendingHumanAction records from domain-specific sources."""

from __future__ import annotations

from core.evidence_service import extract_evidence_ids
from core.governance.action_state import (
    EVIDENCE_POLICY,
    _model_payload,
    add_action_if_missing,
)
from core.models import (
    FlagStatus,
    PendingHumanAction,
    ProjectContext,
)


def create_actions_from_flags(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """把【需核验】低层信号升级为正式 verify_evidence 动作。"""
    created: list[PendingHumanAction] = []
    for flag in ctx.flagged_items:
        if flag.stage != stage or flag.status != FlagStatus.PENDING:
            continue
        action = add_action_if_missing(
            ctx,
            stage_id=stage,
            source_type="flag",
            source_id=flag.item_id,
            action_type="verify_evidence",
            title=f"核验阶段{stage}的不确定内容",
            description=flag.content,
            risk_level="medium",
            trigger_reason="AI 输出中包含【需核验】标记",
            payload_before=_model_payload(flag),
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_failure_modes(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """阶段一 high/critical 失败模式需要人工处理后才能继续。"""
    if stage != 1 or not ctx.stage_1_output:
        return []

    created: list[PendingHumanAction] = []
    for fm in ctx.stage_1_output.failure_modes:
        severity = str(fm.severity).lower()
        if severity not in {"high", "critical"}:
            continue
        action_type = "escalate" if severity == "critical" else "approve"
        action = add_action_if_missing(
            ctx,
            stage_id=1,
            source_type="failure_mode",
            source_id=fm.id,
            action_type=action_type,
            title=f"确认高风险失败模式：{fm.id}",
            description=f"{fm.category}：{fm.description}",
            risk_level=severity,
            trigger_reason=f"阶段一识别到 {severity} 风险失败模式",
            payload_before=_model_payload(fm),
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_evidence_gaps(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Create severity-aware evidence review actions.

    high/critical failure modes must have enough evidence, must not rely only on
    weak sources, and must be manually verified before automatic continuation.
    """
    if stage != 1 or not ctx.stage_1_output:
        return []

    evidence_by_id = {ev.evidence_id: ev for ev in ctx.evidence_sources}
    created: list[PendingHumanAction] = []
    for fm in ctx.stage_1_output.failure_modes:
        severity = str(fm.severity).lower()
        policy = EVIDENCE_POLICY.get(severity, EVIDENCE_POLICY["medium"])
        evidence_ids = list(
            dict.fromkeys(
                (getattr(fm, "evidence_ids", []) or []) + extract_evidence_ids(fm.evidence)
            )
        )
        min_count = int(policy["min_evidence_count"])
        min_score = float(policy["min_credibility_score"])
        blocking = bool(policy["blocking"])

        if len(evidence_ids) < min_count:
            action = add_action_if_missing(
                ctx,
                stage_id=1,
                source_type="evidence_gap",
                source_id=fm.id,
                action_type="edit",
                title=f"补充失败模式证据引用：{fm.id}",
                description=f"{fm.category}：{fm.description}",
                risk_level=severity,
                trigger_reason="失败模式没有满足 evidence_id 数量要求，必须编辑 Stage1 structured_output 补充 evidence_ids",
                payload_before={
                    "failure_mode": _model_payload(fm),
                    "required_min_evidence_count": min_count,
                    "found_evidence_ids": evidence_ids,
                    "requires_structured_output": True,
                    "expected_schema": "Stage1Schema",
                },
                blocking=blocking,
                stage_output_version=stage_output_version,
            )
            if action:
                created.append(action)
            continue

        weak_sources = [
            ev
            for ev_id in evidence_ids
            if (ev := evidence_by_id.get(ev_id)) is not None
            and (ev.credibility_score < min_score or ev.source_type in {"unknown", "forum"})
        ]
        if weak_sources and severity in {"medium", "high", "critical"}:
            action = add_action_if_missing(
                ctx,
                stage_id=1,
                source_type="evidence_low_credibility",
                source_id=fm.id,
                action_type="verify_evidence",
                title=f"核验低可信证据：{fm.id}",
                description=f"失败模式 {fm.id} 引用了低可信、论坛或未知来源证据。",
                risk_level=severity,
                trigger_reason="风险结论依赖低可信/未知来源",
                payload_before={
                    "failure_mode": _model_payload(fm),
                    "required_min_credibility_score": min_score,
                    "weak_sources": [_model_payload(ev) for ev in weak_sources],
                },
                blocking=blocking,
                stage_output_version=stage_output_version,
            )
            if action:
                created.append(action)

        unverified_sources = [
            ev
            for ev_id in evidence_ids
            if (ev := evidence_by_id.get(ev_id)) is not None and not ev.verified
        ]
        if unverified_sources and severity in {"high", "critical"}:
            action = add_action_if_missing(
                ctx,
                stage_id=1,
                source_type="evidence_unverified_for_high_risk",
                source_id=fm.id,
                action_type="verify_evidence",
                title=f"人工核验高风险证据：{fm.id}",
                description=f"高风险失败模式 {fm.id} 的证据尚未人工核验。",
                risk_level=severity,
                trigger_reason="high/critical 失败模式引用的证据未人工核验",
                payload_before={
                    "failure_mode": _model_payload(fm),
                    "unverified_sources": [_model_payload(ev) for ev in unverified_sources],
                },
                blocking=True,
                stage_output_version=stage_output_version,
            )
            if action:
                created.append(action)
    return created


def create_actions_from_workflow_policies(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """根据 Stage 2 WorkflowNode.oversight_policy 创建正式人工动作。"""
    if stage != 2 or not ctx.stage_2_output:
        return []

    created: list[PendingHumanAction] = []
    for node in ctx.stage_2_output.workflow_nodes:
        policy = node.oversight_policy
        if policy is None:
            continue
        if policy.can_auto_continue and policy.risk_level not in {"high", "critical"}:
            continue

        required_action = policy.required_action
        if policy.risk_level == "critical":
            required_action = "escalate"
        action = add_action_if_missing(
            ctx,
            stage_id=2,
            source_type="oversight_policy",
            source_id=policy.policy_id,
            node_id=node.node_id,
            action_type=required_action,
            title=f"处理节点 {node.node_id} 的人工监督策略",
            description=policy.trigger_reason,
            risk_level=policy.risk_level,
            trigger_reason=policy.trigger_reason,
            payload_before={
                "node": _model_payload(node),
                "policy": _model_payload(policy),
            },
            blocking=not policy.can_auto_continue,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_policy_gaps(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Stage 2 policy gap: high-risk failure modes must be covered by policy."""
    if stage != 2 or not ctx.stage_1_output or not ctx.stage_2_output:
        return []

    high_risk_ids = {
        fm.id
        for fm in ctx.stage_1_output.failure_modes
        if str(fm.severity).lower() in {"high", "critical"}
    }
    if not high_risk_ids:
        return []

    severity_by_fm = {
        fm.id: fm.severity
        for fm in ctx.stage_1_output.failure_modes
        if str(fm.severity).lower() in {"high", "critical"}
    }
    covered: set[str] = set()
    created: list[PendingHumanAction] = []

    for node in ctx.stage_2_output.workflow_nodes:
        addressed = set(node.failure_modes_addressed or [])
        high_risk_addressed = addressed.intersection(high_risk_ids)
        covered.update(high_risk_addressed)
        if high_risk_addressed and node.oversight_policy is None:
            action = add_action_if_missing(
                ctx,
                stage_id=2,
                source_type="policy_gap",
                source_id=node.node_id,
                node_id=node.node_id,
                action_type="edit",
                title=f"补充节点 {node.node_id} 的监督策略",
                description=f"节点 {node.node_id} 覆盖高风险 failure_mode {', '.join(sorted(high_risk_addressed))}，但缺少 HumanOversightPolicy。",
                risk_level="high",
                trigger_reason="高风险节点缺少监督策略",
                payload_before={
                    "node": _model_payload(node),
                    "failure_mode_ids": sorted(high_risk_addressed),
                    "requires_structured_output": True,
                    "expected_schema": "Stage2Schema",
                    "gap_type": "missing_oversight_policy",
                },
                blocking=True,
                stage_output_version=stage_output_version,
            )
            if action:
                created.append(action)

    for failure_mode_id in sorted(high_risk_ids - covered):
        severity = severity_by_fm.get(failure_mode_id, "high")
        action = add_action_if_missing(
            ctx,
            stage_id=2,
            source_type="policy_gap",
            source_id=failure_mode_id,
            action_type="edit",
            title=f"补充高风险 failure_mode {failure_mode_id} 的工作流覆盖",
            description=f"阶段2没有 workflow node 覆盖高风险 failure_mode：{failure_mode_id}。",
            risk_level=str(severity).lower(),
            trigger_reason="高风险 failure_mode 未被工作流覆盖",
            payload_before={
                "failure_mode_id": failure_mode_id,
                "severity": str(severity),
                "requires_structured_output": True,
                "expected_schema": "Stage2Schema",
                "gap_type": "uncovered_high_risk_failure_mode",
            },
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    return created


def create_actions_from_stage3_result(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """阶段三整体未通过时，要求人工编辑或回退工作流。"""
    if stage != 3 or not ctx.stage_3_output:
        return []
    if ctx.stage_3_output.overall_passed:
        return []

    action = add_action_if_missing(
        ctx,
        stage_id=3,
        source_type="stress_test",
        source_id="stage_3_overall",
        action_type="edit",
        title="处理阶段三压测未通过结果",
        description="阶段三整体压测未通过，需要人工决定修改压测输入、回退工作流设计或带风险继续。",
        risk_level="high",
        trigger_reason="阶段三整体压测结果为未通过",
        payload_before=_model_payload(ctx.stage_3_output),
        blocking=True,
        stage_output_version=stage_output_version,
    )
    return [action] if action else []


def create_actions_from_trace_backfill_gaps(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Stage 3 trace backfill gaps: failed traces must be backfilled as EvalCases."""
    if stage != 3:
        return []

    from core.trace_backfill_service import build_trace_backfill_summary

    summary = build_trace_backfill_summary(ctx)
    created: list[PendingHumanAction] = []

    for trace_id in summary.get("eligible_trace_ids_without_eval_case", []) or []:
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="trace_backfill_gap",
            source_id=trace_id,
            action_type="approve",
            title=f"回填追踪记录为评测用例：{trace_id}",
            description=f"失败/解析错误/安全类追踪记录 {trace_id} 尚未回填为评测用例。",
            risk_level="high",
            trigger_reason="追踪记录未回填为评测用例",
            payload_before={"gap_type": "trace_without_eval_case", "trace_id": trace_id, **summary},
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    for eval_id in summary.get("backfilled_eval_ids_without_trace_dataset", []) or []:
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="trace_backfill_gap",
            source_id=eval_id,
            action_type="approve",
            title=f"将评测用例纳入追踪数据集：{eval_id}",
            description=f"追踪回填的评测用例 {eval_id} 尚未纳入生产追踪评测数据集。",
            risk_level="high",
            trigger_reason="评测用例未纳入追踪数据集",
            payload_before={
                "gap_type": "trace_eval_case_without_dataset",
                "eval_id": eval_id,
                **summary,
            },
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    return created


def create_actions_from_eval_regression(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Stage 3 eval regression: blocking regression decisions require human action."""
    if stage != 3:
        return []

    from core.eval_regression_policy import build_stage_regression_decisions
    from core.gates.risk_profile import build_stage3_gate_profile

    profile = build_stage3_gate_profile(ctx)
    dataset_by_id = {ds.dataset_id: ds for ds in getattr(ctx, "eval_datasets", []) or []}

    created: list[PendingHumanAction] = []
    for decision in build_stage_regression_decisions(ctx, stage=stage):
        if not decision.blocking:
            continue
        if not profile.require_eval_regression:
            dataset = dataset_by_id.get(decision.dataset_id)
            dataset_gate_required = bool(dataset and (dataset.metadata or {}).get("gate_required"))
            if not dataset_gate_required:
                continue

        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="eval_regression",
            source_id=decision.source_id or decision.dataset_id or "",
            action_type="edit",
            title=f"处理评测回归：{decision.dataset_id}",
            description=decision.message,
            risk_level=decision.severity or "high",
            trigger_reason="评测实验回归，需要人工处理",
            payload_before={
                **decision.metadata,
                "decision_status": decision.status,
                "dataset_id": decision.dataset_id,
                "experiment_id": decision.experiment_id,
                "baseline_experiment_id": decision.baseline_experiment_id,
                "required_resolution": decision.required_resolution,
            },
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    return created


def _risk_for_failure_mode_ids(ctx: ProjectContext, failure_mode_ids: list[str]) -> str:
    severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    highest = "medium"
    if not ctx.stage_1_output:
        return highest
    severity_by_id = {fm.id: str(fm.severity).lower() for fm in ctx.stage_1_output.failure_modes}
    for failure_mode_id in failure_mode_ids:
        severity = severity_by_id.get(failure_mode_id, "medium")
        if severity_order.get(severity, 1) > severity_order.get(highest, 1):
            highest = severity
    return highest


def _high_risk_node_ids_for_eval(ctx: ProjectContext) -> set[str]:
    from core.coverage.policy import required_high_risk_node_ids

    return required_high_risk_node_ids(ctx)


def create_actions_from_eval_failures(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Create review actions when Stage 3 eval gates need human closure."""
    if stage != 3:
        return []

    created: list[PendingHumanAction] = []
    high_risk_nodes = _high_risk_node_ids_for_eval(ctx)
    covered_nodes = {case.target_node_id for case in ctx.eval_cases if case.target_node_id}

    for node_id in sorted(high_risk_nodes - covered_nodes):
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="eval_coverage",
            source_id=node_id,
            action_type="edit",
            title=f"补充高风险节点 EvalCase 覆盖：{node_id}",
            description="阶段三推进前，每个高风险工作流节点都必须至少有一条评测用例（EvalCase）。",
            risk_level="high",
            trigger_reason="高风险工作流节点缺少阶段三评测用例覆盖。",
            node_id=node_id,
            payload_before={
                "target_node_id": node_id,
                "missing_eval_coverage": True,
                "requires_structured_output": True,
                "expected_schema": "Stage3Schema",
            },
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    for case in ctx.eval_cases:
        if case.passed is not False:
            continue
        risk_level = _risk_for_failure_mode_ids(ctx, case.covered_failure_mode_ids or [])
        action_type = (
            "escalate"
            if risk_level == "critical"
            else "edit"
            if risk_level == "high"
            else "approve"
        )
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="eval_case",
            source_id=case.eval_id,
            action_type=action_type,
            title=f"处理未通过的评测用例：{case.eval_id}",
            description=f"节点 {case.target_node_id or '未知'} 的评测用例未通过。",
            risk_level=risk_level,
            trigger_reason="评测用例未通过（passed=False）",
            node_id=case.target_node_id,
            payload_before=_model_payload(case),
            blocking=risk_level in {"high", "critical"},
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    for run in ctx.eval_runs:
        failed = run.judge_result == "failed" or run.status == "failed"
        needs_review = run.judge_result == "needs_review"
        if not (failed or needs_review):
            continue
        risk_level = _risk_for_failure_mode_ids(ctx, run.covered_failure_mode_ids or [])
        is_high_risk_path = (
            risk_level in {"high", "critical"} or run.target_node_id in high_risk_nodes
        )
        if needs_review and not is_high_risk_path:
            continue
        action_type = (
            "escalate"
            if risk_level == "critical"
            else "edit"
            if risk_level == "high"
            else "approve"
        )
        title_prefix = (
            "Review required eval run" if needs_review and not failed else "Resolve failed eval run"
        )
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="eval_run",
            source_id=run.run_id,
            action_type=action_type,
            title=f"{title_prefix}: {run.run_id}",
            description=(
                f"EvalRun for eval {run.eval_id} on node {run.target_node_id or 'unknown'} "
                f"returned judge_result={run.judge_result} status={run.status}."
            ),
            risk_level="high"
            if needs_review and risk_level not in {"high", "critical"}
            else risk_level,
            trigger_reason=run.judge_reason or run.error_message or "EvalRun requires human review",
            node_id=run.target_node_id,
            payload_before=_model_payload(run),
            blocking=is_high_risk_path,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    return created


def create_actions_from_trigger_methods(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """Stage 4 trigger method 若声明需要人工审核，则创建 approve 动作。"""
    if stage != 4 or not ctx.stage_4_output:
        return []

    created: list[PendingHumanAction] = []
    for method in ctx.stage_4_output.trigger_methods:
        if not getattr(method, "human_review_required", False):
            continue
        action = add_action_if_missing(
            ctx,
            stage_id=4,
            source_type="trigger_method",
            source_id=method.node_id,
            node_id=method.node_id,
            action_type="approve",
            title=f"确认触发方式需要人工审核：{method.node_id}",
            description=method.execution_suggestion or method.trigger_instruction,
            risk_level="high",
            trigger_reason="该触发方式被标记为需要人工复核",
            payload_before=_model_payload(method),
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_safety_findings(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """high/critical safety finding 会阻断自动推进。"""
    created: list[PendingHumanAction] = []
    for finding in ctx.safety_findings:
        if finding.stage_id != stage or finding.status != "open":
            continue
        if finding.severity not in {"high", "critical"} or not finding.requires_human_review:
            continue
        action_type = "escalate" if finding.severity == "critical" else "approve"
        action = add_action_if_missing(
            ctx,
            stage_id=stage,
            source_type="safety_finding",
            source_id=finding.finding_id,
            action_type=action_type,
            title=f"处理安全发现：{finding.risk_type}",
            description=finding.description,
            risk_level=finding.severity,
            trigger_reason=finding.recommended_action,
            payload_before=_model_payload(finding),
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)
    return created


def create_actions_from_redteam_gaps(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """阶段3红队测试覆盖不足时，创建人工动作引导用户处理。"""
    if stage != 3:
        return []

    from core.redteam_service import build_redteam_coverage_summary

    summary = build_redteam_coverage_summary(ctx, stage=stage)
    created: list[PendingHumanAction] = []

    if summary.get("missing_safety_finding_ids"):
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="redteam_gap",
            source_id="missing_safety_coverage",
            action_type="approve",
            title="红队测试覆盖不足：高风险安全发现缺少对抗用例",
            description=f"共有 {len(summary.get('missing_safety_finding_ids', []))} 个高风险安全发现缺少 RedTeamCase 覆盖。需要生成对抗用例来验证系统在这些风险场景下的安全性。",
            risk_level="high",
            trigger_reason="红队测试覆盖不足",
            payload_before={"gap_type": "missing_safety_redteam_case", **summary},
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    if summary.get("missing_node_ids"):
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="redteam_gap",
            source_id="missing_node_coverage",
            action_type="approve",
            title="红队测试覆盖不足：高风险工作流节点缺少对抗用例",
            description=f"共有 {len(summary.get('missing_node_ids', []))} 个高风险工作流节点缺少 RedTeamCase 覆盖。",
            risk_level="high",
            trigger_reason="红队测试覆盖不足",
            payload_before={"gap_type": "missing_node_redteam_case", **summary},
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    for case_id in summary.get("draft_high_case_ids", []) or []:
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="redteam_case",
            source_id=case_id,
            action_type="approve",
            title=f"批准红队用例：{case_id}",
            description=f"高风险 RedTeamCase {case_id} 仍为 draft，需人工批准后才能进入 Eval。",
            risk_level="high",
            trigger_reason="红队用例待批准",
            payload_before={"gap_type": "draft_redteam_case", "case_id": case_id, **summary},
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    for case_id in summary.get("approved_unsynced_case_ids", []) or []:
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="redteam_case",
            source_id=case_id,
            action_type="approve",
            title=f"同步红队用例到 Eval：{case_id}",
            description=f"已批准 RedTeamCase {case_id} 尚未同步为 EvalCase。",
            risk_level="high",
            trigger_reason="红队用例待同步",
            payload_before={
                "gap_type": "approved_redteam_case_not_synced",
                "case_id": case_id,
                **summary,
            },
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    if summary.get("synced_eval_ids_without_redteam_dataset"):
        action = add_action_if_missing(
            ctx,
            stage_id=3,
            source_type="redteam_gap",
            source_id="missing_redteam_dataset",
            action_type="approve",
            title="创建红队评测数据集",
            description=f"共有 {len(summary.get('synced_eval_ids_without_redteam_dataset', []))} 个红队评测用例尚未进入 redteam_generated EvalDataset。",
            risk_level="high",
            trigger_reason="缺少红队评测数据集",
            payload_before={"gap_type": "redteam_eval_case_not_in_dataset", **summary},
            blocking=True,
            stage_output_version=stage_output_version,
        )
        if action:
            created.append(action)

    return created


def create_actions_from_parser_errors(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """结构化解析失败时，创建人工编辑动作。"""
    error = ctx.parser_errors.get(f"stage_{stage}")
    if not error:
        return []

    output = getattr(ctx, f"stage_{stage}_output", None)
    action = add_action_if_missing(
        ctx,
        stage_id=stage,
        source_type="parser",
        source_id=f"stage_{stage}",
        action_type="edit",
        title=f"修复阶段{stage}结构化解析失败",
        description="AI 输出无法稳定解析为目标结构，需要人工编辑或要求模型重跑。",
        risk_level="high",
        trigger_reason=error,
        payload_before={
            "stage_output": _model_payload(output),
            "parser_error": error,
            "requires_structured_output": True,
            "expected_schema": f"Stage{stage}Schema",
        },
        blocking=True,
        stage_output_version=stage_output_version,
    )
    return [action] if action else []


def create_review_actions_for_stage(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> list[PendingHumanAction]:
    """统一入口：根据阶段输出创建所有必要人工动作。"""
    created: list[PendingHumanAction] = []
    created.extend(create_actions_from_flags(ctx, stage, stage_output_version=stage_output_version))
    created.extend(
        create_actions_from_failure_modes(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_evidence_gaps(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_workflow_policies(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_policy_gaps(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_stage3_result(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_eval_failures(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_trace_backfill_gaps(
            ctx, stage, stage_output_version=stage_output_version
        )
    )
    created.extend(
        create_actions_from_eval_regression(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_trigger_methods(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_safety_findings(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_parser_errors(ctx, stage, stage_output_version=stage_output_version)
    )
    created.extend(
        create_actions_from_redteam_gaps(ctx, stage, stage_output_version=stage_output_version)
    )
    return created
