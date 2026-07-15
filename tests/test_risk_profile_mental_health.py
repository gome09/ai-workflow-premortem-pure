"""T1.2 回归测试：university_mental_health 场景必须升为 HIGH 及以上。"""

from core.gates.risk_profile import ProjectGateRiskTier, classify_project_risk
from core.models import ProjectContext


def _build_mental_health_ctx() -> ProjectContext:
    """复刻 examples/university_ai_mental_health_input.md 的关键词分布。"""
    return ProjectContext(
        research_target="基于多源行为数据的学生心理健康风险预测系统",
        domain="高校学生事务管理",
        goal="早期识别存在心理健康风险的学生，向心理咨询中心发出预警",
    )


def test_mental_health_scenario_raises_to_high():
    ctx = _build_mental_health_ctx()
    tier, reasons = classify_project_risk(ctx)
    assert tier in {ProjectGateRiskTier.HIGH, ProjectGateRiskTier.CRITICAL}, (
        f"university_mental_health should be HIGH+, got {tier}; reasons={reasons}"
    )
    assert any("mental health" in r or "student" in r for r in reasons)


def test_non_mental_health_session_stays_medium():
    """无关键词的普通会话仍为 MEDIUM（防回归）。"""
    ctx = ProjectContext(
        research_target="内部知识库问答",
        domain="企业内部工具",
        goal="提升员工查找文档效率",
    )
    tier, _ = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.MEDIUM
