# tests/test_sensitive_personal_floor.py
"""sensitive_personal 风险地板值回归测试（2026-09-01 修复）。

此前缺口：classify_project_risk 中 low-scope 降档在 sensitive_personal 升档
（3.5 步）之后执行，敏感个人数据项目可被降回 MEDIUM 甚至 LOW。
修复：sensitive_personal 升档引入 tier floor（HIGH），第 4/5 步降档尊重 floor。
背景见 .upgrade/STATE.md Blockers 与 docs/spec/data-classification-and-privacy.md。
"""

from __future__ import annotations

from core.gates.risk_profile import (
    ProjectGateRiskTier,
    build_stage3_gate_profile,
    classify_project_risk,
)
from core.models import ProjectContext, SessionState


def _ctx(
    research_target: str,
    domain: str = "",
    goal: str = "",
    data_classification: str = "sensitive_personal",
) -> ProjectContext:
    return ProjectContext(
        research_target=research_target,
        domain=domain,
        goal=goal,
        current_state=SessionState.S2_REVIEW,
        data_classification=data_classification,
    )


def test_sensitive_personal_with_low_scope_stays_high():
    """敏感个人数据 + low-scope 词 + 无领域关键词：地板值 HIGH，不得落 LOW/MEDIUM。"""
    ctx = _ctx("个人笔记，本地使用，记录学习心得")
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.HIGH
    assert any("sensitive_personal" in r for r in reasons)


def test_sensitive_personal_low_scope_not_downgraded_to_medium():
    """敏感个人数据 + low-scope：3.5 步升到 HIGH 后，第 4 步降档必须尊重 floor。"""
    ctx = _ctx("个人日记与草稿整理工具")
    tier, _ = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.HIGH


def test_sensitive_personal_with_sensitive_keyword_reaches_critical():
    """敏感个人数据 + 敏感数据关键词（身份信息）：MEDIUM→HIGH（关键词）→CRITICAL（3.5 步）。"""
    ctx = _ctx("记录身份信息与证件号码的个人助手")
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.CRITICAL
    assert any("sensitive_data" in r for r in reasons)
    assert any("sensitive_personal" in r for r in reasons)


def test_sensitive_personal_with_high_domain_keyword_reaches_critical():
    """敏感个人数据 + 高风险领域（心理健康）+ low-scope：CRITICAL 不被降档。"""
    ctx = _ctx("个人心理健康记录与自杀风险自查工具")
    tier, _ = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.CRITICAL


def test_floor_does_not_affect_normal_low_scope():
    """非敏感分类 + low-scope + 无领域关键词：正常降 LOW（行为不变）。"""
    ctx = _ctx("个人读书与学习计划管理系统", data_classification="business_internal")
    tier, _ = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.LOW


def test_floor_high_gate_profile_blocks_redteam():
    """地板值 HIGH 的项目拿到 HIGH 档 profile：红队覆盖回归为 blocking。"""
    ctx = _ctx("个人笔记，本地使用，记录学习心得")
    profile = build_stage3_gate_profile(ctx)
    assert profile.risk_tier == ProjectGateRiskTier.HIGH
    assert profile.require_redteam_coverage is True
