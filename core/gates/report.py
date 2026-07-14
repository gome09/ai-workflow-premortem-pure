# core/gates/report.py
"""Gate decision path visualisation — report models and builder."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

# ─────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────


class RuleDetail(BaseModel):
    rule_id: str
    display_name: str
    status: Literal["passed", "blocked", "skipped"]
    severity: Literal["critical", "high", "medium", "low"] | None = None
    reason: str | None = None  # populated when blocked
    skipped_reason: str | None = None  # populated when skipped
    rule_version: str = "0.0.0"  # T3.2: carried from manifest for governance provenance


class GateReportSummary(BaseModel):
    total: int
    passed: int
    blocked: int
    skipped: int


class GateReport(BaseModel):
    session_id: str
    stage: int
    risk_profile: str  # low | medium | high | critical
    overall: Literal["passed", "blocked"]
    evaluated_at: datetime
    rules: list[RuleDetail]
    summary: GateReportSummary


# ─────────────────────────────────────────────
# Internal per-rule result carrier
# ─────────────────────────────────────────────


class _RuleEvalRecord:
    """Transient, not serialised — used only inside engine.py."""

    __slots__ = (
        "rule_id",
        "display_name",
        "status",
        "severity",
        "reason",
        "skipped_reason",
        "rule_version",
    )

    def __init__(
        self,
        rule_id: str,
        display_name: str,
        status: Literal["passed", "blocked", "skipped"],
        severity: str | None = None,
        reason: str | None = None,
        skipped_reason: str | None = None,
        rule_version: str = "0.0.0",
    ) -> None:
        self.rule_id = rule_id
        self.display_name = display_name
        self.status = status
        self.severity = severity
        self.reason = reason
        self.skipped_reason = skipped_reason
        self.rule_version = rule_version


# ─────────────────────────────────────────────
# Display name derivation
# ─────────────────────────────────────────────

# Explicit human-readable names; fall back to title-cased rule_id.
_DISPLAY_NAMES: dict[str, str] = {
    "missing_output": "缺少阶段结果",
    "stale_dependency": "依赖已过期",
    "action_state": "待处理 / 已驳回动作",
    "parser_error": "解析失败",
    "safety_finding": "待处理安全发现",
    "stage1_evidence_gap": "阶段一证据缺口",
    "stage2_policy_gap": "阶段二策略缺口",
    "stage3_eval_failure": "阶段三评测失败",
    "redteam_coverage": "红队覆盖",
    "eval_regression": "评测回归",
    "trace_backfill_gap": "追踪回填缺口",
    "stage4_final_governance": "阶段四最终治理",
}


def _display_name(rule_id: str) -> str:
    return _DISPLAY_NAMES.get(rule_id, rule_id.replace("_", " ").title())


# ─────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────


def build_report(
    *,
    session_id: str,
    stage: int,
    risk_profile: str,
    rule_records: list[_RuleEvalRecord],
    overall_passed: bool,
    evaluated_at: datetime | None = None,
) -> GateReport:
    """Construct a GateReport from collected per-rule records."""
    if evaluated_at is None:
        evaluated_at = datetime.now(tz=UTC)

    rules: list[RuleDetail] = []
    passed_count = 0
    blocked_count = 0
    skipped_count = 0

    for rec in rule_records:
        severity: Any = rec.severity
        # Normalise severity to allowed literals or None.
        if severity not in {"critical", "high", "medium", "low"}:
            severity = None

        rules.append(
            RuleDetail(
                rule_id=rec.rule_id,
                display_name=rec.display_name,
                status=rec.status,
                severity=severity,
                reason=rec.reason,
                skipped_reason=rec.skipped_reason,
                rule_version=rec.rule_version,
            )
        )
        if rec.status == "passed":
            passed_count += 1
        elif rec.status == "blocked":
            blocked_count += 1
        else:
            skipped_count += 1

    return GateReport(
        session_id=session_id,
        stage=stage,
        risk_profile=risk_profile,
        overall="passed" if overall_passed else "blocked",
        evaluated_at=evaluated_at,
        rules=rules,
        summary=GateReportSummary(
            total=len(rules),
            passed=passed_count,
            blocked=blocked_count,
            skipped=skipped_count,
        ),
    )
