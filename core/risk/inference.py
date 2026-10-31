# core/risk/inference.py
"""Deterministic inference of risk factors from legacy free-text context.

This is a compatibility adapter, not the classification authority. It maps the
historic keyword signals onto the six structured factors so existing sessions
keep their previous LOW/MEDIUM/HIGH/CRITICAL behaviour until explicit factor
scores (human or scenario) are supplied.
"""

from __future__ import annotations

import re

from core.models import ProjectContext
from core.risk.models import RiskFactorScores

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


def _matching_reasons(text: str, patterns: list[tuple[re.Pattern[str], str]]) -> list[str]:
    return [reason for pattern, reason in patterns if pattern.search(text)]


def aggregate_legacy_text(ctx: ProjectContext) -> str:
    """Combine the free-text fields historically used for keyword scanning."""
    parts = [
        ctx.research_target or "",
        ctx.domain or "",
        ctx.goal or "",
    ]
    if ctx.stage_1_output:
        for failure_mode in ctx.stage_1_output.failure_modes:
            parts.append(failure_mode.description or "")
            parts.append(failure_mode.category or "")
    return " ".join(parts)


def infer_legacy_factors(ctx: ProjectContext) -> tuple[RiskFactorScores, list[str]]:
    """Map historic keyword signals onto six factor scores.

    Returns ``(factors, reasons)``. Reasons preserve the established labels used
    by existing tests and reports (e.g. ``critical: healthcare/medical domain``).
    """
    text = aggregate_legacy_text(ctx)
    reasons: list[str] = []

    impact = 1
    autonomy = 1
    data_sensitivity = 1
    reversibility = 1
    scale = 1
    external_exposure = 1

    critical_hits = _matching_reasons(text, _CRITICAL_KEYWORDS)
    high_hits = _matching_reasons(text, _HIGH_KEYWORDS)

    if critical_hits:
        reasons.extend(f"critical: {hit}" for hit in critical_hits)
        impact = 3
        autonomy = max(autonomy, 2)
        data_sensitivity = 3
        reversibility = max(reversibility, 2)
        scale = max(scale, 2)
    elif high_hits:
        reasons.extend(f"high: {hit}" for hit in high_hits)
        impact = max(impact, 2)
        data_sensitivity = max(data_sensitivity, 2)
        reversibility = max(reversibility, 2)

    automation_hits = _matching_reasons(text, _HIGH_AUTOMATION_KEYWORDS)
    sensitive_hits = _matching_reasons(text, _SENSITIVE_DATA_KEYWORDS)

    low_hits = _matching_reasons(text, _LOW_SCOPE_KEYWORDS)
    if low_hits:
        reasons.extend(f"low_scope: {hit}" for hit in low_hits)
        # Critical-domain projects keep their risk floor even when the wording
        # also suggests a personal/demo scope (historic behaviour). High-domain
        # projects keep impact/data/reversibility but drop autonomy/scale/exposure.
        if not critical_hits and high_hits:
            autonomy = max(autonomy - 1, 0)
            scale = max(scale - 1, 0)
            external_exposure = max(external_exposure - 1, 0)
        elif not critical_hits:
            impact = max(impact - 1, 0)
            autonomy = max(autonomy - 1, 0)
            data_sensitivity = max(data_sensitivity - 1, 0)
            reversibility = max(reversibility - 1, 0)
            scale = max(scale - 1, 0)
            external_exposure = max(external_exposure - 1, 0)

    if automation_hits:
        reasons.extend(f"automation: {hit}" for hit in automation_hits)
        autonomy = max(autonomy, 2)

    if sensitive_hits:
        reasons.extend(f"sensitive_data: {hit}" for hit in sensitive_hits)
        data_sensitivity = 3
        impact = max(impact, 2)

    if getattr(ctx, "data_classification", "business_internal") == "sensitive_personal":
        reasons.append("sensitive_personal data classification")
        data_sensitivity = max(data_sensitivity, 2)

    if not reasons:
        reasons.append(
            "no explicit domain/automation/sensitivity keywords found; defaulting to medium"
        )

    factors = RiskFactorScores(
        impact=impact,
        autonomy=autonomy,
        data_sensitivity=data_sensitivity,
        reversibility=reversibility,
        scale=scale,
        external_exposure=external_exposure,
        rationale="legacy keyword inference",
        source="legacy_inference",
    )
    return factors, reasons
