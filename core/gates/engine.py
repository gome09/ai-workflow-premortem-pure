# core/gates/engine.py
from __future__ import annotations

import logging
from typing import Any

from core.gates.rules import registered_rules
from core.models import LLMTrace, ProjectContext
from core.stage_readiness_service import StageBlocker, StageGateResult, _current_version

logger = logging.getLogger(__name__)


class GateDataError(RuntimeError):
    """HIGH/CRITICAL gate evidence could not be persisted.

    For high-risk sessions the governance record is part of the safety
    contract, so a persistence failure must block advancement instead of
    being swallowed as a non-fatal side effect.
    """


def _strict_gate_persistence(ctx: ProjectContext) -> bool:
    from core.gates.risk_profile import requires_strict_structured_output

    return requires_strict_structured_output(ctx)


def _rule_error_blocker(
    ctx: ProjectContext, stage: int, rule_id: str, *, data_error: bool = False
) -> StageBlocker:
    if data_error:
        return StageBlocker(
            blocker_id=f"S{stage}_GATE_DATA_ERROR_{rule_id}",
            stage_id=stage,
            stage_output_version=_current_version(ctx, stage),
            blocker_type="gate_data_error",
            rule_id=rule_id,
            severity="critical",
            message="gate evaluation persistence failed",
            source_type="gate_evaluation_records",
            source_id=rule_id,
            required_resolution="retry_gate_persistence",
            can_be_overridden_by_approval=False,
            metadata={"error": "gate_evaluation_persistence_failed"},
        )
    return StageBlocker(
        blocker_id=f"S{stage}_GATE_RULE_ERROR_{rule_id}",
        stage_id=stage,
        stage_output_version=_current_version(ctx, stage),
        blocker_type="gate_rule_error",
        rule_id=rule_id,
        severity="critical",
        message="rule evaluation failed",
        source_type="gate_rule",
        source_id=rule_id,
        required_resolution="rerun_stage",
        can_be_overridden_by_approval=False,
        metadata={"error": "rule_evaluation_failed"},
    )


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
) -> LLMTrace:
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

    # T3.3 规则禁用治理：解析显式禁用集合；安全底线规则忽略禁用并告警
    from core.config import settings
    from core.gates.rules.manifest import is_safety_bottom_line

    disabled = settings.gate_rules_disabled_set

    # Imports deferred to avoid circular imports at module load time.
    if detailed:
        from core.gates.report import (
            GateReport,
            _display_name,
            _RuleEvalRecord,
            build_report,
        )
        from core.gates.risk_profile import classify_project_risk
        from core.gates.rules.manifest import get_rule_version

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
                        rule_version=get_rule_version(rule.rule_id),
                    )
                )
            continue

        # T3.3 规则禁用治理
        if rule.rule_id in disabled:
            if is_safety_bottom_line(rule.rule_id):
                logger.warning(
                    "Rule %s is safety-bottom-line; GATE_RULES_DISABLED entry ignored.",
                    rule.rule_id,
                )
            else:
                if detailed:
                    rule_records.append(
                        _RuleEvalRecord(
                            rule_id=rule.rule_id,
                            display_name=_display_name(rule.rule_id),
                            status="skipped",
                            skipped_reason="Rule disabled via GATE_RULES_DISABLED.",
                            rule_version=get_rule_version(rule.rule_id),
                        )
                    )
                continue

        evaluated_rule_ids.append(rule.rule_id)
        try:
            rule_blockers = rule.evaluate(ctx, stage)
        except GateDataError:
            logger.warning(
                "Gate rule %s raised GateDataError; emitting deterministic data blocker.",
                rule.rule_id,
                exc_info=True,
            )
            rule_blockers = [_rule_error_blocker(ctx, stage, rule.rule_id, data_error=True)]
        except Exception:
            # 规则异常不能穿透到 API：统一转为确定性 critical blocker（fail-closed）。
            logger.warning(
                "Gate rule %s failed; emitting deterministic rule-error blocker.",
                rule.rule_id,
                exc_info=True,
            )
            rule_blockers = [_rule_error_blocker(ctx, stage, rule.rule_id)]

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
                        rule_version=get_rule_version(rule.rule_id),
                    )
                )
            else:
                rule_records.append(
                    _RuleEvalRecord(
                        rule_id=rule.rule_id,
                        display_name=_display_name(rule.rule_id),
                        status="passed",
                        rule_version=get_rule_version(rule.rule_id),
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

    # T3.2 旁路落表：治理趋势数据源，失败不阻断主路径
    _try_persist_gate_evaluation(ctx, stage, deduped)

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


def _try_persist_gate_evaluation(
    ctx: ProjectContext, stage: int, blockers: list[StageBlocker]
) -> None:
    """旁路写入 gate_evaluation_records——治理趋势数据源。

    非高风险会话失败只打日志（治理数据缺一行可接受，评估被卡死不可接受）。
    HIGH/CRITICAL 会话的 Gate 证据缺失会破坏可审计性，strict 下写表失败抛
    `GateDataError`，由 readiness 转为确定性阻断。
    """
    strict = _strict_gate_persistence(ctx)
    blocking_rule_ids: list[str] = []
    try:
        from core.config import settings
        from core.gates.risk_profile import classify_project_risk
        from core.gates.rules.manifest import get_rule_version, is_safety_bottom_line
        from storage.session_store import session_store as _store

        session_id = getattr(ctx, "session_id", "") or ""
        if not session_id:
            return
        tenant_id = getattr(ctx, "tenant_id", "") or ""
        risk_tier, _ = classify_project_risk(ctx)
        blocking_rule_ids = sorted({b.rule_id for b in blockers if b.rule_id})
        rule_versions = (
            {rid: get_rule_version(rid) for rid in blocking_rule_ids} if blocking_rule_ids else {}
        )
        # T3.3 标注被禁用规则
        disabled = settings.gate_rules_disabled_set
        for rid in disabled:
            if not is_safety_bottom_line(rid):
                rule_versions.setdefault(rid, "disabled")
        _store.record_gate_evaluation(
            session_id=session_id,
            tenant_id=tenant_id,
            stage_id=stage,
            risk_tier=str(risk_tier),
            passed=not blockers,
            blocking_rule_ids=blocking_rule_ids,
            rule_versions=rule_versions,
        )
    except Exception as exc:
        if strict:
            raise GateDataError(
                f"gate_evaluation_records persist failed for stage {stage}"
            ) from exc
        logger.warning("gate_evaluation_records persist failed; non-fatal", exc_info=True)
        return

    # T3.5 业务指标打点（import 在函数内避免循环依赖；失败不阻断）
    try:
        from api.metrics import record_gate_evaluation_metrics

        record_gate_evaluation_metrics(
            passed=not blockers,
            blocking_rule_ids=blocking_rule_ids,
        )
    except Exception:
        logger.debug("record_gate_evaluation_metrics failed; non-fatal", exc_info=True)
