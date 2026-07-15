# tests/test_risk_profile_floor.py
"""WS-7: Domain risk floor — low-scope keywords must not downgrade HIGH/CRITICAL.

Validates the fix in ``core/gates/risk_profile.py``: keywords like "Demo",
"辅助", "学习" should NOT lower a HIGH-domain (e.g. mental health) or
CRITICAL-domain (e.g. medical) project to MEDIUM/LOW.
"""

from __future__ import annotations

from core.gates.risk_profile import (
    ProjectGateRiskTier,
    build_stage3_gate_profile,
    classify_project_risk,
)
from core.models import ProjectContext


def _make_ctx(domain: str, research_target: str = "", goal: str = "") -> ProjectContext:
    ctx = ProjectContext()
    ctx.domain = domain
    ctx.research_target = research_target
    ctx.goal = goal
    return ctx


# ─────────────────────────────────────────────
# HIGH domain floor: mental health
# ─────────────────────────────────────────────


def test_mental_health_with_demo_keyword_stays_high():
    """心理健康 / 危机干预 / 学生辅助学习 Demo — must remain HIGH (not MEDIUM)."""
    ctx = _make_ctx(
        domain="心理健康 / 危机干预 / 学生辅助学习 Demo",
        research_target="高校学生心理健康 AI 辅助系统",
        goal="提供心理健康信息与危机升级",
    )
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.HIGH, f"expected HIGH, got {tier}; reasons={reasons}"
    profile = build_stage3_gate_profile(ctx)
    assert profile.risk_tier == ProjectGateRiskTier.HIGH


def test_mental_health_low_scope_keywords_do_not_downgrade():
    """Each low-scope keyword alone must not downgrade HIGH mental-health domain."""
    low_scope_keywords = ["Demo", "辅助", "学习"]
    for kw in low_scope_keywords:
        ctx = _make_ctx(
            domain=f"心理健康 / 危机干预 / {kw}",
            research_target="学生心理健康系统",
        )
        tier, reasons = classify_project_risk(ctx)
        assert tier == ProjectGateRiskTier.HIGH, (
            f"keyword {kw!r} downgraded mental-health to {tier}; reasons={reasons}"
        )


def test_mental_health_floor_reason_documented():
    """The 'floor' rationale should be surfaced when low-scope keywords are present."""
    ctx = _make_ctx(
        domain="心理健康 / 危机干预 / Demo / 辅助学习",
        research_target="学生心理健康",
    )
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.HIGH
    joined = " ".join(reasons)
    assert "HIGH" in joined.upper() or "下限" in joined, (
        f"floor rationale missing; reasons={reasons}"
    )


# ─────────────────────────────────────────────
# CRITICAL domain floor: medical
# ─────────────────────────────────────────────


def test_medical_domain_with_assist_keyword_stays_critical():
    """医疗健康 / 诊断 / 辅助 — must be CRITICAL (not downgraded by '辅助')."""
    ctx = _make_ctx(
        domain="医疗健康 / 诊断 / 辅助",
        research_target="医疗诊断辅助 AI 系统",
        goal="辅助医生进行临床诊断",
    )
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.CRITICAL, f"expected CRITICAL, got {tier}; reasons={reasons}"
    profile = build_stage3_gate_profile(ctx)
    assert profile.risk_tier == ProjectGateRiskTier.CRITICAL


def test_medical_domain_demo_keyword_stays_critical():
    """医疗 / Demo — must remain CRITICAL."""
    ctx = _make_ctx(
        domain="医疗健康 / 诊断 / Demo",
        research_target="医疗诊断系统",
    )
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.CRITICAL, (
        f"'Demo' downgraded medical domain to {tier}; reasons={reasons}"
    )


# ─────────────────────────────────────────────
# Sanity: low-scope keywords still lower a default MEDIUM project to LOW
# ─────────────────────────────────────────────


def test_low_scope_still_lowers_non_high_domain():
    """Low-scope keywords must still lower a plain MEDIUM project to LOW.

    This guards against over-broadening the floor fix.
    """
    ctx = _make_ctx(
        domain="个人读书笔记 / 学习计划 / 本地使用",
        research_target="个人读书计划管理",
    )
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.LOW, (
        f"plain personal-scope project should be LOW, got {tier}; reasons={reasons}"
    )


# ─────────────────────────────────────────────
# Built-in scenario domains must hit their expected floor
# ─────────────────────────────────────────────


def test_university_mental_health_scenario_domain_is_high_floor():
    """The mental-health scenario's domain text must classify as HIGH at minimum."""
    ctx = _make_ctx(
        domain="心理健康 / 危机干预 / 学生辅助学习 Demo",
        research_target="高校学生心理健康风险预测 AI 系统",
    )
    tier, _ = classify_project_risk(ctx)
    assert tier in {ProjectGateRiskTier.HIGH, ProjectGateRiskTier.CRITICAL}
