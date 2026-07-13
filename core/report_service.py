# core/report_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.audit_service import append_audit_event

# TODO: 报告生成逻辑太复杂了，generate_report 函数有 200+ 行
# 应该拆成 generate_ai_section / generate_eval_section 等子函数
from core.config import settings
from core.eval_judgment_service import build_eval_judgment_summary
from core.eval_regression_policy import build_stage_eval_regression_summary
from core.eval_service import build_eval_summary
from core.execution_mode import WorkflowExecutionMode
from core.models import ProjectContext, ReportArtifact
from core.redteam_service import build_redteam_coverage_summary
from core.report_diff import build_output_diff_summary, build_stage_version_history
from core.stage_advancement_coordinator import build_stage_advancement_decision
from core.stage_readiness_service import build_stage_readiness as _build_stage_readiness
from core.stage_readiness_service import (
    build_unresolved_governance_items as _build_unresolved_governance_items,
)
from core.stage_resolution_service import (
    build_stage_resolution_summary as _build_stage_resolution_summary,
)
from core.trace_backfill_service import build_trace_backfill_summary
from core.version import APP_VERSION, PACKAGE_STAGE, REPORT_SCHEMA_VERSION
from tools.taxonomies.mapper import build_taxonomy_summary


def _dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def build_oversight_summary(ctx: ProjectContext) -> dict:
    actions = ctx.pending_actions
    pending = [a for a in actions if a.status == "pending"]
    resolved = [a for a in actions if a.status == "resolved"]
    rejected = [a for a in resolved if a.reviewer_decision == "reject"]
    escalations = [a for a in actions if a.action_type == "escalate"]
    return {
        "total_actions": len(actions),
        "pending_actions": len(pending),
        "pending_blocking_actions": len([a for a in pending if a.blocking]),
        "resolved_actions": len(resolved),
        "rejected_actions": len(rejected),
        "superseded_actions": len([a for a in actions if a.status == "superseded"]),
        "critical_escalations": len([a for a in escalations if a.risk_level == "critical"]),
    }


def build_evidence_summary(ctx: ProjectContext) -> dict:
    failure_modes = ctx.stage_1_output.failure_modes if ctx.stage_1_output else []
    without_evidence = [
        fm.id for fm in failure_modes if not (getattr(fm, "evidence_ids", []) or [])
    ]
    low_credibility = [
        ev.evidence_id
        for ev in ctx.evidence_sources
        if ev.credibility_score < 0.4 or ev.source_type == "unknown"
    ]
    verified_sources = [ev for ev in ctx.evidence_sources if ev.verified]
    return {
        "total_evidence_sources": len(ctx.evidence_sources),
        "verified_sources": len(verified_sources),
        "low_credibility_sources": len(low_credibility),
        "low_credibility_evidence_ids": low_credibility,
        "failure_modes_total": len(failure_modes),
        "failure_modes_without_evidence": without_evidence,
        "failure_modes_without_evidence_count": len(without_evidence),
    }


def build_stage_lineage_summary(ctx: ProjectContext) -> dict:
    """Expose stage version lineage and staleness in audit-ready reports."""
    stale_stage_outputs = {
        key: value
        for key, value in getattr(ctx, "stage_staleness", {}).items()
        if isinstance(value, dict) and value.get("stale")
    }
    return {
        "stage_output_versions": dict(getattr(ctx, "stage_output_versions", {}) or {}),
        "stage_dependency_versions": dict(getattr(ctx, "stage_dependency_versions", {}) or {}),
        "stale_stage_outputs": stale_stage_outputs,
    }


def build_report_export_status(
    ctx: ProjectContext, stage_readiness: dict, unresolved_governance_items: dict
) -> dict:
    """Return whether the current report snapshot should be treated as audit-ready."""
    blockers = unresolved_governance_items.get("stage_blockers", [])
    hard_blockers = [
        blocker for blocker in blockers if not blocker.get("can_be_overridden_by_approval", False)
    ]
    stale_outputs = [
        key
        for key, value in getattr(ctx, "stage_staleness", {}).items()
        if isinstance(value, dict) and value.get("stale")
    ]
    allowed = (
        not hard_blockers
        and not stale_outputs
        and not unresolved_governance_items.get("parser_errors")
    )
    reason = ""
    if stale_outputs:
        reason = f"stale stage outputs exist: {', '.join(sorted(stale_outputs))}"
    elif hard_blockers:
        reason = f"{len(hard_blockers)} hard stage blocker(s) unresolved"
    elif unresolved_governance_items.get("parser_errors"):
        reason = "parser errors unresolved"
    return {
        "allowed": allowed,
        "reason": reason,
        "stale_stage_outputs": stale_outputs,
        "hard_blocker_count": len(hard_blockers),
    }


def build_execution_summary(ctx: ProjectContext) -> dict:
    records = getattr(ctx, "interrupt_records", []) or []
    pending = [record for record in records if record.status == "pending"]
    resumed = [record for record in records if record.status == "resumed"]
    cancelled = [record for record in records if record.status == "cancelled"]
    consumed = [record for record in resumed if record.resume_consumed_at is not None]
    pending_resume = [record for record in resumed if record.resume_consumed_at is None]
    mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
    adapter_level = (
        "checkpoint_interrupt"
        if mode == WorkflowExecutionMode.LANGGRAPH_INTERRUPT
        else "mapping_only"
    )
    resume_failed = [
        event
        for event in getattr(ctx, "audit_events", [])
        if event.event_type == "interrupt_resume_failed"
    ]
    return {
        "execution_mode": mode.value,
        "adapter_level": adapter_level,
        "interrupt_adapter_status": (
            "LangGraph interrupt/checkpoint path is enabled by WORKFLOW_EXECUTION_MODE."
            if mode == WorkflowExecutionMode.LANGGRAPH_INTERRUPT
            else "single_step is the stable default; interrupt records remain an auditable mapping layer."
        ),
        "interrupt_records_total": len(records),
        "pending_interrupts": len(pending),
        "resumed_interrupts": len(resumed),
        "cancelled_interrupts": len(cancelled),
        "resume_consumed_count": len(consumed),
        "pending_resume_count": len(pending_resume),
        "resume_error_count": len(resume_failed),
    }


def build_stage_readiness(ctx: ProjectContext) -> dict:
    """Report-compatible wrapper around the unified stage readiness service."""
    return _build_stage_readiness(ctx)


def build_unresolved_governance_items(ctx: ProjectContext) -> dict:
    """Report-compatible wrapper around the unified governance summary."""
    return _build_unresolved_governance_items(ctx)


def build_stage_resolution_summary(ctx: ProjectContext) -> dict:
    """Report-compatible wrapper around concrete blocker resolution operations."""
    return _build_stage_resolution_summary(ctx)


def build_stage_advancement_summary(
    ctx: ProjectContext,
    stage_readiness: dict,
    stage_resolution_summary: dict,
    unresolved_governance_items: dict,
) -> dict:
    """Compact stage-advancement summary for report/API consumers."""
    blockers = unresolved_governance_items.get("stage_blockers", []) or []
    blocker_rule_counts: dict[str, int] = {}
    for blocker in blockers:
        rule_id = blocker.get("rule_id") or "unknown"
        blocker_rule_counts[rule_id] = blocker_rule_counts.get(rule_id, 0) + 1

    logs = getattr(ctx, "action_resolution_logs", []) or []
    result_status_counts: dict[str, int] = {}
    for log in logs:
        result_status_counts[log.result_status] = result_status_counts.get(log.result_status, 0) + 1

    traces = getattr(ctx, "llm_traces", []) or []
    trace_type_counts: dict[str, int] = {}
    parser_status_counts: dict[str, int] = {}
    for trace in traces:
        trace_type_counts[trace.trace_type] = trace_type_counts.get(trace.trace_type, 0) + 1
        parser_status_counts[trace.parser_status] = (
            parser_status_counts.get(trace.parser_status, 0) + 1
        )

    return {
        "package_stage": PACKAGE_STAGE,
        "stage_gate_status": {
            key: {
                "can_continue": value.get("can_continue"),
                "stage_output_version": value.get("stage_output_version"),
                "blocker_count": len(value.get("blockers", []) or []),
                "stage_lifecycle": value.get("stage_lifecycle"),
            }
            for key, value in stage_readiness.items()
        },
        "gate_rule_summary": {
            "open_blocker_count": len(blockers),
            "blocker_rule_counts": blocker_rule_counts,
        },
        "action_resolution_summary": {
            "attempt_count": len(logs),
            "result_status_counts": result_status_counts,
        },
        "trace_summary": {
            "trace_count": len(traces),
            "trace_type_counts": trace_type_counts,
            "parser_status_counts": parser_status_counts,
        },
        "current_required_operations": stage_resolution_summary.get(
            "current_required_operations", []
        ),
        "operation_executability_summary": {
            "total_operations": stage_resolution_summary.get("total_operations", 0),
            "executable_operations_count": stage_resolution_summary.get(
                "executable_operations_count", 0
            ),
            "hard_blockers_count": stage_resolution_summary.get("hard_blockers_count", 0),
            "overridable_blockers_count": stage_resolution_summary.get(
                "overridable_blockers_count", 0
            ),
            "missing_api_binding_operations": [
                op
                for op in stage_resolution_summary.get("current_required_operations", [])
                if (op.get("metadata") or {}).get("contract_api_capable") and not op.get("api_path")
            ],
        },
    }


def build_report_dict(ctx: ProjectContext) -> dict:
    """生成 audit-ready JSON 报告。"""
    actions = [_dump(action) for action in ctx.pending_actions]
    open_actions = [a for a in actions if a.get("status") == "pending"]
    resolved_actions = [a for a in actions if a.get("status") == "resolved"]
    eval_summary = build_eval_summary(ctx)
    eval_regression_summary = build_stage_eval_regression_summary(ctx, stage=3)
    redteam_coverage_summary = build_redteam_coverage_summary(ctx, stage=3)
    taxonomy_summary = build_taxonomy_summary(ctx)
    eval_judgment_summary = build_eval_judgment_summary(ctx)
    trace_backfill_summary = build_trace_backfill_summary(ctx)
    redteam_cases = [_dump(case) for case in getattr(ctx, "redteam_cases", []) or []]
    eval_datasets = [_dump(dataset) for dataset in getattr(ctx, "eval_datasets", [])]
    eval_experiments = [_dump(experiment) for experiment in getattr(ctx, "eval_experiments", [])]
    eval_runs = [_dump(run) for run in ctx.eval_runs]
    interrupt_records = [_dump(record) for record in getattr(ctx, "interrupt_records", []) or []]
    oversight_summary = build_oversight_summary(ctx)
    evidence_summary = build_evidence_summary(ctx)
    execution_summary = build_execution_summary(ctx)
    stage_readiness = build_stage_readiness(ctx)
    unresolved_governance_items = build_unresolved_governance_items(ctx)
    stage_resolution_summary = build_stage_resolution_summary(ctx)
    stage_advancement_decisions_by_stage = {
        f"stage_{stage}": build_stage_advancement_decision(
            ctx,
            stage,
            decision_source="stage_gate",
            reason="report_stage_advancement_snapshot",
            append_trace=False,
        ).model_dump(mode="json")
        for stage in range(1, 5)
    }
    next_required_operation = (
        stage_resolution_summary.get("current_required_operations") or [None]
    )[0]
    stage_lineage = build_stage_lineage_summary(ctx)
    report_export_status = build_report_export_status(
        ctx, stage_readiness, unresolved_governance_items
    )
    stage_advancement_summary = build_stage_advancement_summary(
        ctx,
        stage_readiness,
        stage_resolution_summary,
        unresolved_governance_items,
    )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.utcnow().isoformat(),
        "session_id": ctx.session_id,
        "created_at": ctx.created_at.isoformat(),
        "updated_at": ctx.updated_at.isoformat(),
        "current_state": ctx.current_state.value,
        "project_info": {
            "research_target": ctx.research_target,
            "domain": ctx.domain,
            "goal": ctx.goal,
        },
        "ai_generated": {
            "stage_1": _dump(ctx.stage_1_output),
            "stage_2": _dump(ctx.stage_2_output),
            "stage_3": _dump(ctx.stage_3_output),
            "stage_4": _dump(ctx.stage_4_output),
        },
        "human_reviewed": ctx.reviewed_outputs,
        "flagged_items": [_dump(flag) for flag in ctx.flagged_items],
        "evidence_sources": [_dump(ev) for ev in ctx.evidence_sources],
        "safety_findings": [_dump(finding) for finding in ctx.safety_findings],
        "eval_cases": [_dump(case) for case in ctx.eval_cases],
        "redteam_cases": redteam_cases,
        "redteam_coverage_summary": redteam_coverage_summary,
        "taxonomy_summary": taxonomy_summary,
        "eval_judgments": [_dump(item) for item in getattr(ctx, "eval_judgments", []) or []],
        "human_calibrations": [
            _dump(item) for item in getattr(ctx, "human_calibrations", []) or []
        ],
        "eval_judgment_summary": eval_judgment_summary,
        "trace_backfill_summary": trace_backfill_summary,
        "v0_8_closure_summary": {
            "package_stage": PACKAGE_STAGE,
            "app_version": APP_VERSION,
            "taxonomy_mapping_ready": not taxonomy_summary.get("unmapped_safety_finding_ids")
            and not taxonomy_summary.get("unmapped_redteam_case_ids"),
            "eval_judgment_count": eval_judgment_summary.get("judgment_count", 0),
            "human_calibration_count": eval_judgment_summary.get("human_calibration_count", 0),
            "trace_backfilled_eval_case_count": trace_backfill_summary.get(
                "backfilled_eval_case_count", 0
            ),
            "runtime_validation": "deferred_by_instruction",
        },
        "eval_datasets": eval_datasets,
        "eval_experiments": eval_experiments,
        "eval_regression_summary": eval_regression_summary,
        "eval_runs": eval_runs,
        "failed_eval_runs": [
            run
            for run in eval_runs
            if run.get("judge_result") == "failed" or run.get("status") == "failed"
        ],
        "eval_summary": eval_summary,
        "oversight_summary": oversight_summary,
        "evidence_summary": evidence_summary,
        "execution_summary": execution_summary,
        "stage_readiness": stage_readiness,
        "stage_advancement_summary": stage_advancement_summary,
        "stage_advancement_decisions_by_stage": stage_advancement_decisions_by_stage,
        "stage_lineage": stage_lineage,
        "report_export_status": report_export_status,
        "unresolved_governance_items": unresolved_governance_items,
        "stage_resolution_summary": stage_resolution_summary,
        "next_required_operation": next_required_operation,
        "interrupt_records": interrupt_records,
        "stage_version_summary": build_stage_version_history(ctx),
        "output_diffs": build_output_diff_summary(ctx),
        "open_risks": [
            _dump(finding)
            for finding in ctx.safety_findings
            if getattr(finding, "status", "") == "open"
        ],
        "open_actions": open_actions,
        "resolved_actions": resolved_actions,
        "all_actions": actions,
        "audit_events": [_dump(event) for event in ctx.audit_events],
        "review_notes": ctx.review_notes,
        "parser_errors": ctx.parser_errors,
        "stage_output_versions": ctx.stage_output_versions,
        "stage_dependency_versions": getattr(ctx, "stage_dependency_versions", {}),
        "stage_staleness": getattr(ctx, "stage_staleness", {}),
        "disclaimer": "AI-generated outputs must be reviewed by humans before real-world use.",
    }


def create_report_artifact(ctx: ProjectContext) -> ReportArtifact:
    """生成并保留版本化报告快照。"""
    content = build_report_dict(ctx)
    content_md = build_markdown_report(ctx)
    artifact = ReportArtifact(
        session_id=ctx.session_id,
        version=REPORT_SCHEMA_VERSION,
        ai_generated=content.get("ai_generated", {}),
        human_reviewed=content.get("human_reviewed", {}),
        evidence=content.get("evidence_sources", []),
        audit_events=content.get("audit_events", []),
        open_risks=content.get("open_risks", []),
        eval_summary=content.get("eval_summary", {}),
        eval_runs=content.get("eval_runs", []),
        failed_eval_runs=content.get("failed_eval_runs", []),
        content_json=content,
        content_markdown=content_md,
    )
    ctx.report_artifacts.append(artifact)
    append_audit_event(
        ctx,
        actor="system",
        event_type="report_artifact_created",
        target_type="report_artifact",
        target_id=artifact.report_id,
        after=artifact,
        metadata={"version": artifact.version},
    )
    return artifact


def _append_json_block(lines: list[str], title: str, value: Any) -> None:
    import json

    lines.append(f"### {title}")
    lines.append("```json")
    lines.append(json.dumps(value, ensure_ascii=False, indent=2))
    lines.append("```")


def build_markdown_report(ctx: ProjectContext) -> str:
    """生成便于人工审阅的 Markdown 报告。"""
    report = build_report_dict(ctx)
    info = report["project_info"]
    lines: list[str] = [
        "# AI Workflow Pre-mortem Report",
        "",
        f"- Report Schema Version: `{REPORT_SCHEMA_VERSION}`",
        f"- Session ID: `{ctx.session_id}`",
        f"- Generated At: {report['generated_at']}",
        f"- Current State: `{report['current_state']}`",
        "",
        "## 0. Stage Readiness",
    ]

    stage_readiness = report.get("stage_readiness", {})
    if stage_readiness:
        for key, value in stage_readiness.items():
            state = "ready" if value.get("can_continue") else "blocked"
            lines.append(
                f"- **{key}** v{value.get('stage_output_version')} {state}: "
                f"pending_blocking={len(value.get('pending_blocking_action_ids') or [])}"
            )
            if value.get("block_reason"):
                lines.append(f"  - Block reason: {value['block_reason']}")
            if value.get("parser_error"):
                lines.append(f"  - Parser error: {value['parser_error']}")
    else:
        lines.append("No stage readiness summary available.")

    resolution_summary = report.get("stage_resolution_summary", {})
    current_operations = resolution_summary.get("current_required_operations") or []
    lines.extend(["", "## 0.1 Stage Resolution Operations"])
    if current_operations:
        lines.append(
            f"- Total operations: {resolution_summary.get('total_operations', len(current_operations))}"
        )
        lines.append(f"- Hard blockers: {resolution_summary.get('hard_blockers_count', 0)}")
        lines.append(
            f"- Overridable blockers: {resolution_summary.get('overridable_blockers_count', 0)}"
        )
        for op in current_operations[:20]:
            lines.append(
                f"- `{op.get('operation_id')}` stage={op.get('stage_id')} "
                f"[{op.get('severity')}/{op.get('blocker_type')}] "
                f"resolution={op.get('required_resolution')}"
            )
            lines.append(f"  - Next action: {op.get('frontend_hint')}")
            if op.get("api_path"):
                lines.append(f"  - API: {op.get('api_method')} {op.get('api_path')}")
            elif op.get("api_hint"):
                lines.append(f"  - API hint: {op.get('api_hint')}")
    else:
        lines.append("No blocker resolution operations are currently required.")

    lines.extend(
        [
            "",
            "## 1. Project Overview",
            f"- Research Target: {info['research_target']}",
            f"- Domain: {info['domain']}",
            f"- Goal: {info['goal']}",
            "",
            "## 2. Oversight & Evidence Summary",
        ]
    )

    oversight_summary = report.get("oversight_summary", {})
    evidence_summary = report.get("evidence_summary", {})
    for key, value in oversight_summary.items():
        lines.append(f"- Oversight {key}: {value}")
    for key, value in evidence_summary.items():
        lines.append(f"- Evidence {key}: {value}")

    lines.extend(
        [
            "",
            "## 3. Failure Modes",
        ]
    )

    if ctx.stage_1_output and ctx.stage_1_output.failure_modes:
        for fm in ctx.stage_1_output.failure_modes:
            evidence_ids = ", ".join(fm.evidence_ids or []) or "none"
            lines.append(f"- **{fm.id}** [{fm.severity}] {fm.category}: {fm.description}")
            lines.append(f"  - Evidence IDs: {evidence_ids}")
            if fm.evidence:
                lines.append(f"  - Evidence Text: {fm.evidence}")
    else:
        lines.append("No structured failure modes available.")

    lines.extend(["", "## 4. Workflow Design"])
    if ctx.stage_2_output and ctx.stage_2_output.workflow_nodes:
        for node in ctx.stage_2_output.workflow_nodes:
            policy = node.oversight_policy
            lines.append(f"- **{node.node_id}** {node.stage_name} / model={node.model_assigned}")
            lines.append(f"  - Human Action: {node.human_action}")
            lines.append(
                f"  - Failure Modes Addressed: {', '.join(node.failure_modes_addressed or []) or 'none'}"
            )
            lines.append(f"  - Check Criteria: {node.check_criteria}")
            if policy:
                lines.append(
                    f"  - Oversight Policy: risk={policy.risk_level}, action={policy.required_action}, "
                    f"auto_continue={policy.can_auto_continue}, evidence_required={policy.evidence_required}"
                )
            else:
                lines.append("  - Oversight Policy: none")
    else:
        lines.append("No structured workflow nodes available.")

    lines.extend(["", "## 5. Stress Test Cases"])
    if ctx.stage_3_output and ctx.stage_3_output.test_results:
        for case in ctx.stage_3_output.test_results:
            status = "passed" if case.passed else "failed"
            lines.append(f"- **{case.tested_node_id}** [{case.scenario_type}/{status}]")
            lines.append(f"  - Test Input: {case.test_input}")
            if case.error_predictions:
                lines.append(f"  - Error Predictions: {'; '.join(case.error_predictions)}")
            if case.correction_prompts:
                lines.append(f"  - Correction Prompts: {'; '.join(case.correction_prompts)}")
            if case.pass_criteria:
                lines.append(f"  - Pass Criteria: {'; '.join(case.pass_criteria)}")
    else:
        lines.append("No structured stress test cases available.")

    lines.extend(["", "## 6. Trigger Methods"])
    if ctx.stage_4_output and ctx.stage_4_output.trigger_methods:
        for method in ctx.stage_4_output.trigger_methods:
            review = "required" if method.human_review_required else "not required"
            lines.append(
                f"- **{method.node_id}** mode={method.model_or_mode}, human_review={review}"
            )
            lines.append(f"  - Entry Point: {method.entry_point}")
            lines.append(f"  - Trigger Instruction: {method.trigger_instruction}")
            lines.append(f"  - Execution Suggestion: {method.execution_suggestion}")
    else:
        lines.append("No structured trigger methods available.")

    lines.extend(["", "## 7. Evidence Sources"])
    if ctx.evidence_sources:
        for ev in ctx.evidence_sources:
            verified = "verified" if ev.verified else "unverified"
            lines.append(
                f"- `{ev.evidence_id}` [{ev.source_type}] score={ev.credibility_score} "
                f"status={verified}: {ev.title}"
            )
            if ev.url:
                lines.append(f"  - URL: {ev.url}")
            if ev.used_by_failure_mode_ids:
                lines.append(f"  - Used by: {', '.join(ev.used_by_failure_mode_ids)}")
    else:
        lines.append("No evidence sources recorded.")

    lines.extend(["", "## 8. Safety Findings"])
    if ctx.safety_findings:
        for finding in ctx.safety_findings:
            lines.append(
                f"- `{finding.finding_id}` stage={finding.stage_id} "
                f"[{finding.severity}/{finding.risk_type}] status={finding.status}: {finding.description}"
            )
            lines.append(f"  - Recommended Action: {finding.recommended_action}")
            if finding.resolution_note:
                lines.append(f"  - Resolution Note: {finding.resolution_note}")
    else:
        lines.append("No safety findings recorded.")

    lines.extend(["", "## 9. Human Oversight Actions"])
    if report["all_actions"]:
        for action in report["all_actions"]:
            lines.append(
                f"- `{action['action_id']}` stage={action['stage_id']} "
                f"type={action['action_type']} status={action['status']} risk={action['risk_level']} "
                f"blocking={action.get('blocking')}"
            )
            if action.get("trigger_reason"):
                lines.append(f"  - Trigger: {action['trigger_reason']}")
            if action.get("reviewer_decision"):
                lines.append(f"  - Decision: {action['reviewer_decision']}")
    else:
        lines.append("No human actions recorded.")

    lines.extend(["", "## 10. Execution / Interrupt Records"])
    execution_summary = report.get("execution_summary", {})
    if execution_summary:
        for key, value in execution_summary.items():
            lines.append(f"- {key}: {value}")
    interrupt_records = report.get("interrupt_records", [])
    if interrupt_records:
        for record in interrupt_records:
            lines.append(
                f"- `{record.get('interrupt_id')}` action={record.get('action_id')} "
                f"stage={record.get('stage_id')} v{record.get('stage_output_version')} "
                f"status={record.get('status')}"
            )
            if record.get("thread_id"):
                lines.append(f"  - thread_id: {record.get('thread_id')}")
            if record.get("node_name"):
                lines.append(f"  - node_name: {record.get('node_name')}")
            if record.get("resume_consumed_at"):
                lines.append(f"  - resume_consumed_at: {record.get('resume_consumed_at')}")
            elif record.get("status") == "resumed":
                lines.append("  - resume_consumed_at: pending")
    else:
        lines.append("No interrupt records recorded.")

    lines.extend(["", "## 11. Open Risks"])
    open_risks = report.get("open_risks", [])
    open_actions = report.get("open_actions", [])
    if open_risks or open_actions:
        if open_risks:
            lines.append("### Open Safety Findings")
            for risk in open_risks:
                lines.append(
                    f"- `{risk['finding_id']}` [{risk['severity']}/{risk['risk_type']}] {risk['description']}"
                )
        if open_actions:
            lines.append("### Pending Human Actions")
            for action in open_actions:
                lines.append(
                    f"- `{action['action_id']}` [{action['risk_level']}/{action['action_type']}] {action['title']}"
                )
    else:
        lines.append("No open risks or pending actions recorded.")

    lines.extend(["", "## 12. Reviewed Outputs"])
    if ctx.reviewed_outputs:
        for key, value in ctx.reviewed_outputs.items():
            _append_json_block(lines, key, value)
    else:
        lines.append("No reviewed outputs recorded.")

    lines.extend(["", "## 13. Parser Errors"])
    if ctx.parser_errors:
        for key, error in ctx.parser_errors.items():
            lines.append(f"- **{key}**: {error}")
    else:
        lines.append("No parser errors recorded.")

    lines.extend(["", "## 14. Stage Version Summary"])
    version_summary = report.get("stage_version_summary", {})
    if version_summary:
        for key, value in version_summary.items():
            lines.append(
                f"- **{key}** version={value.get('current_version')} "
                f"reviewed={value.get('has_reviewed_output')} "
                f"changed_by_human={value.get('changed_by_human')} "
                f"open_parser_error={value.get('open_parser_error')}"
            )
            if value.get("pending_action_ids"):
                lines.append(f"  - Pending Actions: {', '.join(value['pending_action_ids'])}")
            if value.get("edit_action_ids"):
                lines.append(f"  - Edit Actions: {', '.join(value['edit_action_ids'])}")
    else:
        lines.append("No stage version summary available.")

    lines.extend(["", "## 15. Eval Summary"])
    eval_regression_summary = report.get("eval_regression_summary", {})
    if eval_regression_summary:
        lines.append(
            f"- Regression Gate: datasets={eval_regression_summary.get('gate_relevant_dataset_count', 0)} "
            f"blocking={eval_regression_summary.get('blocking_dataset_count', 0)} "
            f"passed={eval_regression_summary.get('passed_dataset_count', 0)}"
        )
        for decision in (eval_regression_summary.get("decisions") or [])[:20]:
            lines.append(
                f"  - `{decision.get('dataset_id')}` status={decision.get('status')} "
                f"blocking={decision.get('blocking')} resolution={decision.get('required_resolution')}"
            )
            if decision.get("message"):
                lines.append(f"    {decision.get('message')}")
    eval_summary = report.get("eval_summary", {})
    if eval_summary:
        for key, value in eval_summary.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("No eval summary available.")

    lines.extend(["", "## 15.1 Taxonomy Mapping"])
    taxonomy_summary = report.get("taxonomy_summary", {})
    if taxonomy_summary:
        lines.append(
            f"- Unmapped SafetyFindings: {len(taxonomy_summary.get('unmapped_safety_finding_ids') or [])}"
        )
        lines.append(
            f"- Unmapped RedTeamCases: {len(taxonomy_summary.get('unmapped_redteam_case_ids') or [])}"
        )
        _append_json_block(lines, "Taxonomy Summary", taxonomy_summary)

    lines.extend(["", "## 15.2 Red Team Coverage"])
    redteam_summary = report.get("redteam_coverage_summary", {})
    redteam_cases = report.get("redteam_cases", [])
    if redteam_summary:
        lines.append(
            f"- RedTeamCases: total={redteam_summary.get('total_cases', 0)} "
            f"draft={redteam_summary.get('draft_cases', 0)} "
            f"approved={redteam_summary.get('approved_cases', 0)} "
            f"synced={redteam_summary.get('synced_cases', 0)} "
            f"blocking={redteam_summary.get('blocking')}"
        )
        if redteam_summary.get("missing_safety_finding_ids"):
            lines.append(
                "- Missing safety coverage: "
                + ", ".join(redteam_summary.get("missing_safety_finding_ids") or [])
            )
        if redteam_summary.get("missing_node_ids"):
            lines.append(
                "- Missing node coverage: "
                + ", ".join(redteam_summary.get("missing_node_ids") or [])
            )
        if redteam_summary.get("synced_eval_ids_without_redteam_dataset"):
            lines.append(
                "- Synced EvalCases not in redteam dataset: "
                + ", ".join(redteam_summary.get("synced_eval_ids_without_redteam_dataset") or [])
            )
    if redteam_cases:
        for case in redteam_cases[:20]:
            lines.append(
                f"- `{case.get('redteam_case_id')}` [{case.get('severity')}/{case.get('status')}] "
                f"attack={case.get('attack_type')} target={case.get('target_node_id') or '-'} "
                f"eval={case.get('linked_eval_case_id') or '-'}"
            )
    else:
        lines.append("No RedTeamCase records available.")

    lines.extend(["", "## 15.3 Eval Judgment / Human Calibration"])
    eval_judgment_summary = report.get("eval_judgment_summary", {})
    if eval_judgment_summary:
        lines.append(f"- Judgments: {eval_judgment_summary.get('judgment_count', 0)}")
        lines.append(
            f"- Human calibrations: {eval_judgment_summary.get('human_calibration_count', 0)}"
        )
        lines.append(
            f"- Judge-human agreement rate: {eval_judgment_summary.get('judge_human_agreement_rate')}"
        )
    trace_backfill_summary = report.get("trace_backfill_summary", {})
    lines.extend(["", "## 15.4 Trace Backfill"])
    if trace_backfill_summary:
        lines.append(
            f"- Backfilled EvalCases: {trace_backfill_summary.get('backfilled_eval_case_count', 0)}"
        )
        lines.append(
            f"- Trace backfill datasets: {', '.join(trace_backfill_summary.get('trace_backfill_dataset_ids') or []) or '-'}"
        )
        if trace_backfill_summary.get("failed_trace_ids_without_eval_case"):
            lines.append(
                "- Failed traces without EvalCase: "
                + ", ".join(trace_backfill_summary.get("failed_trace_ids_without_eval_case") or [])
            )

    lines.extend(["", "## 16. Eval Runs"])
    eval_runs = report.get("eval_runs", [])
    if eval_runs:
        for run in eval_runs:
            lines.append(
                f"- `{run['run_id']}` eval={run['eval_id']} node={run.get('target_node_id')} "
                f"mode={run.get('run_mode')} status={run.get('status')} "
                f"judge={run.get('judge_result')} judge_mode={run.get('judge_mode')}"
            )
            if run.get("violated_criteria"):
                lines.append(f"  - Violated Criteria: {'; '.join(run['violated_criteria'])}")
            if run.get("judge_reason"):
                lines.append(f"  - Judge Reason: {run['judge_reason']}")
            if run.get("error_message"):
                lines.append(f"  - Error: {run['error_message']}")
    else:
        lines.append("No eval runs recorded.")

    lines.extend(["", "## 17. Unresolved Governance Items"])
    unresolved = report.get("unresolved_governance_items", {})
    if unresolved:
        pending_actions = unresolved.get("pending_actions") or []
        open_safety = unresolved.get("open_high_critical_safety_findings") or []
        parser_errors = unresolved.get("parser_errors") or {}
        unverified_evidence = unresolved.get("unverified_high_risk_evidence") or []
        failed_eval_items = unresolved.get("failed_eval_items") or []
        stage_blockers = unresolved.get("stage_blockers") or []
        lines.append(f"- Pending actions: {len(pending_actions)}")
        for action in pending_actions[:20]:
            lines.append(
                f"  - `{action.get('action_id')}` [{action.get('risk_level')}/{action.get('action_type')}] {action.get('title')}"
            )
        lines.append(f"- Open high/critical safety findings: {len(open_safety)}")
        for finding in open_safety[:20]:
            lines.append(
                f"  - `{finding.get('finding_id')}` [{finding.get('severity')}/{finding.get('risk_type')}] {finding.get('description')}"
            )
        lines.append(f"- Parser errors: {len(parser_errors)}")
        for key, error in parser_errors.items():
            lines.append(f"  - {key}: {error}")
        lines.append(f"- Unverified high-risk evidence references: {len(unverified_evidence)}")
        for item in unverified_evidence[:20]:
            lines.append(
                f"  - FM `{item.get('failure_mode_id')}` → evidence `{item.get('evidence_id')}` (score={item.get('credibility_score')})"
            )
        lines.append(f"- Failed eval items: {len(failed_eval_items)}")
        for item in failed_eval_items[:20]:
            lines.append(
                f"  - `{item.get('id')}` [{item.get('type')}] node={item.get('target_node_id')} judge={item.get('judge_result')} scenario={item.get('scenario_type')}"
            )
        lines.append(f"- Stage blockers: {len(stage_blockers)}")
        for blocker in stage_blockers[:20]:
            lines.append(
                f"  - `{blocker.get('blocker_id')}` [{blocker.get('blocker_type')}/{blocker.get('severity')}] stage={blocker.get('stage_id')} v{blocker.get('stage_output_version')}"
            )
            lines.append(f"    {blocker.get('message')}")
    else:
        lines.append("No unresolved governance summary available.")

    lines.extend(["", "## 18. Audit Events"])
    if ctx.audit_events:
        for event in ctx.audit_events:
            lines.append(
                f"- `{event.event_id}` {event.created_at.isoformat()} "
                f"`{event.event_type}` target={event.target_type}/{event.target_id}"
            )
    else:
        lines.append("No audit events recorded.")

    lines.extend(
        [
            "",
            "## 19. Disclaimer",
            "AI-generated outputs must be reviewed by humans before real-world use.",
        ]
    )
    return "\n".join(lines)
