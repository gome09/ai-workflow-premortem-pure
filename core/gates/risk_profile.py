# core/gates/risk_profile.py
"""Risk-adaptive Stage 3 gate profiling.

Classifies projects into risk tiers based on domain keywords, usage scope,
automation level, and data sensitivity.  Each tier maps to a Stage3GateProfile
that controls which advanced gate rules are blocking vs. advisory.

FIXME: 关键词匹配的方式太粗糙了，应该用 embedding 相似度或者 LLM 分类
不过对于毕设演示来说够用了，后面有时间再优化
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from core.models import ProjectContext

# ─────────────────────────────────────────────
# Risk tiers
# ─────────────────────────────────────────────


class ProjectGateRiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ─────────────────────────────────────────────
# Gate profile
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class Stage3GateProfile:
    """Which advanced Stage 3 gate rules are blocking for this project."""

    risk_tier: ProjectGateRiskTier
    require_eval_coverage: bool
    require_failed_eval_resolution: bool
    require_redteam_coverage: bool
    require_eval_regression: bool
    require_trace_backfill: bool
    require_expert_review: bool
    rationale: str


# ─────────────────────────────────────────────
# Keyword / pattern banks
# ─────────────────────────────────────────────

# Critical-domain keywords → critical tier
_CRITICAL_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?i)(药物|处方|诊断|患者|临床|医疗|药品|用药|drug|medication|prescri|diagnos|patient|clinic|medical|pharma)"
        ),
        "healthcare/medical domain",
    ),
    (
        re.compile(
            r"(?i)(心脏|肿瘤|癌症|手术|急救|ICU|急诊|手术室|anaesthesia|anesthesia|surgery|oncology|cardiology)"
        ),
        "clinical/surgical domain",
    ),
]

# High-domain keywords → high tier
_HIGH_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?i)(金融|贷款|投资|支付|交易|保险|银行|证券|基金|finance|loan|invest|payment|transaction|insurance|bank|securities)"
        ),
        "financial domain",
    ),
    (
        re.compile(
            r"(?i)(法律|合同|诉讼|合规|法规|律师|legal|contract|litigation|compliance|regulatory|attorney)"
        ),
        "legal domain",
    ),
    (re.compile(r"(?i)(儿童|未成年人|kid|child|minor|pediatric)"), "child safety"),
    (
        re.compile(r"(?i)(身份认证|认证|密码|credential|authenticat|password|identity.?verif)"),
        "authentication/identity",
    ),
    (re.compile(r"(?i)(安全控制|access.?control|permission|rbac|acl)"), "access control"),
    (re.compile(r"(?i)(公开发布|public.?publish|multi.?tenant|多租户)"), "public/multi-tenant"),
    (
        re.compile(r"(?i)(自动发送|auto.?send|自动推送|auto.?dispatch|auto.?notify)"),
        "automated dispatch",
    ),
    (re.compile(r"(?i)(核电|核能|军事|武器|nuclear|military|weapon)"), "nuclear/military domain"),
    (
        re.compile(r"(?i)(自动驾驶|车辆控制|autonomous.?driv|vehicle.?control)"),
        "autonomous vehicle",
    ),
    (
        re.compile(
            r"(?i)(心理|精神|抑郁|自杀|自残|self.?harm|mental.?health|心理健康|精神健康|psycholog|psychiatr|suicid|depress)"
        ),
        "mental health domain",
    ),
    (
        re.compile(r"(?i)(学生|student|pupil|校园|campus|高校|大学|university|college)"),
        "student/minor-adjacent population",
    ),
]

# Low-risk scope keywords → lower tier
_LOW_SCOPE_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?i)(个人|personal|本地|local|学习|learn|读书|reading|笔记|note|日记|diary|日记本|journal|计划|plan|爱好|hobby|兴趣|interest)"
        ),
        "personal/learning scope",
    ),
    (
        re.compile(
            r"(?i)(非生产|non.?production|测试|test|演示|demo|原型|prototype|实验|experiment|sandbox)"
        ),
        "non-production scope",
    ),
    (
        re.compile(
            r"(?i)(草稿|draft|提醒|remind|整理|organiz|建议|suggest|参考|reference|辅助|assist)"
        ),
        "low-impact automation",
    ),
]

# High-automation keywords → raise tier
_HIGH_AUTOMATION_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)(自动审批|auto.?approv|自动决策|auto.?decis|自动执行|auto.?execut)"),
        "automated approval/decision",
    ),
    (
        re.compile(
            r"(?i)(自动推荐高影响|auto.?recommend.*(?:高|critical|high)|自动驾驶决策|auto.?pilot)"
        ),
        "high-impact auto-recommendation",
    ),
    (
        re.compile(
            r"(?i)(实时交易|real.?time.*(?:交易|交易|transaction)|实时支付|real.?time.*payment)"
        ),
        "real-time financial",
    ),
]

# Sensitive data keywords → raise tier
_SENSITIVE_DATA_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?i)(患者数据|patient.?data|医疗记录|medical.?record|处方数据|prescription.?data)"
        ),
        "patient/medical data",
    ),
    (
        re.compile(
            r"(?i)(财务数据|financial.?data|账户信息|account.?info|信用卡|credit.?card|银行账户|bank.?account)"
        ),
        "financial data",
    ),
    (
        re.compile(r"(?i)(身份信息|identity.?info|身份证|id.?card|护照|passport|SSN|社会安全)"),
        "identity data",
    ),
    (re.compile(r"(?i)(未成年人数据|minor.?data|儿童信息|child.?info)"), "minor data"),
]


def _text_contains_any(text: str, patterns: list[tuple[re.Pattern[str], str]]) -> list[str]:
    """Return matched reason strings for patterns found in *text*."""
    matches: list[str] = []
    for pattern, reason in patterns:
        if pattern.search(text):
            matches.append(reason)
    return matches


def _aggregate_text(ctx: ProjectContext) -> str:
    """Combine all relevant text fields for keyword scanning."""
    parts = [
        ctx.research_target or "",
        ctx.domain or "",
        ctx.goal or "",
    ]
    # Include failure mode descriptions for domain signal
    if ctx.stage_1_output:
        for fm in ctx.stage_1_output.failure_modes:
            parts.append(fm.description or "")
            parts.append(fm.category or "")
    return " ".join(parts)


# ─────────────────────────────────────────────
# Core classification
# ─────────────────────────────────────────────


def classify_project_risk(ctx: ProjectContext) -> tuple[ProjectGateRiskTier, list[str]]:
    """Return (tier, reasons) for the project described by *ctx*.

    The algorithm:
    1. Scan for critical-domain keywords → CRITICAL.
    2. Scan for high-domain keywords → HIGH (unless already CRITICAL).
    3. Scan for high-automation / sensitive-data keywords → raise one level.
    4. Scan for low-scope keywords → lower one level (min LOW).
    5. Stage 1 failure mode severity is an *input* but not the sole determinant.
    """
    text = _aggregate_text(ctx)
    reasons: list[str] = []

    # 1. Critical domain
    critical_hits = _text_contains_any(text, _CRITICAL_KEYWORDS)
    if critical_hits:
        reasons.extend([f"critical: {h}" for h in critical_hits])
        return ProjectGateRiskTier.CRITICAL, reasons

    # 2. High domain
    high_hits = _text_contains_any(text, _HIGH_KEYWORDS)
    if high_hits:
        reasons.extend([f"high: {h}" for h in high_hits])
        tier = ProjectGateRiskTier.HIGH
    else:
        tier = ProjectGateRiskTier.MEDIUM  # default

    # 3. High automation / sensitive data → raise
    auto_hits = _text_contains_any(text, _HIGH_AUTOMATION_KEYWORDS)
    sensitive_hits = _text_contains_any(text, _SENSITIVE_DATA_KEYWORDS)
    if auto_hits:
        reasons.extend([f"automation: {h}" for h in auto_hits])
        if tier == ProjectGateRiskTier.MEDIUM:
            tier = ProjectGateRiskTier.HIGH
        elif tier == ProjectGateRiskTier.HIGH:
            tier = ProjectGateRiskTier.CRITICAL
    if sensitive_hits:
        reasons.extend([f"sensitive_data: {h}" for h in sensitive_hits])
        if tier == ProjectGateRiskTier.MEDIUM:
            tier = ProjectGateRiskTier.HIGH
        elif tier == ProjectGateRiskTier.HIGH:
            tier = ProjectGateRiskTier.CRITICAL

    # 3.5 Sensitive personal data classification → raise to at least HIGH
    if getattr(ctx, "data_classification", None) == "sensitive_personal":
        reasons.append("sensitive_personal data classification")
        if tier == ProjectGateRiskTier.MEDIUM:
            tier = ProjectGateRiskTier.HIGH
        elif tier == ProjectGateRiskTier.HIGH:
            tier = ProjectGateRiskTier.CRITICAL

    # 4. Low scope → lower one level
    low_hits = _text_contains_any(text, _LOW_SCOPE_KEYWORDS)
    if low_hits:
        reasons.extend([f"low_scope: {h}" for h in low_hits])
        if tier == ProjectGateRiskTier.CRITICAL:
            # Critical stays critical even with low-scope signals
            pass
        elif tier == ProjectGateRiskTier.HIGH:
            tier = ProjectGateRiskTier.MEDIUM
        elif tier == ProjectGateRiskTier.MEDIUM:
            tier = ProjectGateRiskTier.LOW

    # 5. If no domain keyword matched and we're still MEDIUM with low-scope signals, go LOW
    if not high_hits and not critical_hits and low_hits:
        tier = ProjectGateRiskTier.LOW

    if not reasons:
        reasons.append(
            "no explicit domain/automation/sensitivity keywords found; defaulting to medium"
        )

    return tier, reasons


def build_stage3_gate_profile(ctx: ProjectContext) -> Stage3GateProfile:
    """Build the Stage 3 gate profile for the current project context."""
    tier, reasons = classify_project_risk(ctx)
    rationale = "; ".join(reasons)

    if tier == ProjectGateRiskTier.CRITICAL:
        return Stage3GateProfile(
            risk_tier=tier,
            require_eval_coverage=True,
            require_failed_eval_resolution=True,
            require_redteam_coverage=True,
            require_eval_regression=True,
            require_trace_backfill=True,
            require_expert_review=True,
            rationale=f"Critical-risk project. {rationale}",
        )

    if tier == ProjectGateRiskTier.HIGH:
        return Stage3GateProfile(
            risk_tier=tier,
            require_eval_coverage=True,
            require_failed_eval_resolution=True,
            require_redteam_coverage=True,
            require_eval_regression=True,  # blocking if gate-relevant dataset exists
            require_trace_backfill=True,  # blocking for failed/parser/safety trace
            require_expert_review=False,
            rationale=f"High-risk project. {rationale}",
        )

    if tier == ProjectGateRiskTier.MEDIUM:
        return Stage3GateProfile(
            risk_tier=tier,
            require_eval_coverage=True,
            require_failed_eval_resolution=True,
            require_redteam_coverage=False,  # only blocking if high/critical safety finding exists
            require_eval_regression=False,  # only blocking if gate_required dataset exists
            require_trace_backfill=False,  # only blocking for failed/parser/safety trace
            require_expert_review=False,
            rationale=f"Medium-risk project. {rationale}",
        )

    # LOW
    return Stage3GateProfile(
        risk_tier=tier,
        require_eval_coverage=True,  # basic eval coverage still expected
        require_failed_eval_resolution=True,  # failed evals need handling
        require_redteam_coverage=False,
        require_eval_regression=False,
        require_trace_backfill=False,
        require_expert_review=False,
        rationale=f"Low-risk project. {rationale}",
    )
