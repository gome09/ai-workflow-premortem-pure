# tests/test_expert_review_gate_v110.py
"""T3.3 expert_review 门禁规则 + 规则禁用治理契约测试。

覆盖：
- CRITICAL 场景产出 expert_review blocker 并创建 escalate 动作
- 幂等：再次评估不重复创建动作
- 动作 approved 后不再阻断
- HIGH/MEDIUM/LOW 场景无 expert_review blocker
- GATE_RULES_DISABLED 跳过普通规则（redteam_coverage）
- GATE_RULES_DISABLED 对安全底线规则（missing_output）忽略禁用
- registered_rules() 返回 13 条（含 expert_review）
- manifest 双向完整性
"""

from __future__ import annotations

import pytest

from core.config import settings
from core.gates.engine import evaluate_stage_gate
from core.gates.risk_profile import ProjectGateRiskTier, build_stage3_gate_profile
from core.gates.rules import registered_rules
from core.gates.rules.manifest import RULE_MANIFEST, is_safety_bottom_line
from core.models import (
    FailureMode,
    HumanOversightPolicy,
    ProjectContext,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    WorkflowNode,
)
from storage.backends.sqlite_store import SQLiteSessionStore

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def sqlite_store(tmp_path, monkeypatch):
    """Fresh isolated SQLite store, patched as the global session_store."""
    db_path = str(tmp_path / "test_expert_review.db")
    store = SQLiteSessionStore(db_path=db_path)
    store.initialize()
    monkeypatch.setattr("storage.session_store.session_store", store)
    return store


@pytest.fixture(autouse=True)
def _reset_disabled(monkeypatch):
    """每个用例前后保证 gate_rules_disabled 为空，避免相互污染。"""
    monkeypatch.setattr(settings, "gate_rules_disabled", "")
    yield
    monkeypatch.setattr(settings, "gate_rules_disabled", "")


# ─────────────────────────────────────────────
# Context builders
# ─────────────────────────────────────────────


def _critical_medication_ctx() -> ProjectContext:
    """CRITICAL-risk: medication management system (triggers expert_review)."""
    ctx = ProjectContext(
        research_target="药物管理系统",
        domain="医疗健康 / 药房协作 / 患者用药",
        goal="管理患者用药记录和药物交互检查",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.session_id = "sess-expert-critical"
    ctx.tenant_id = "tenant-expert"
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-M1",
                category="药物交互",
                description="药物交互检查遗漏导致患者风险",
                severity="critical",
            ),
            FailureMode(
                id="FM-M2",
                category="剂量错误",
                description="处方剂量计算错误",
                severity="high",
            ),
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-interact",
                stage_name="药物交互检查",
                model_assigned="llm",
                human_action="approve",
                check_criteria="交互检查完整",
                failure_modes_addressed=["FM-M1"],
                prompt_template="检查药物交互",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="critical",
                    trigger_reason="FM-M1",
                    required_action="escalate",
                ),
            ),
            WorkflowNode(
                node_id="N-dose",
                stage_name="剂量计算",
                model_assigned="llm",
                human_action="approve",
                check_criteria="剂量正确",
                failure_modes_addressed=["FM-M2"],
                prompt_template="计算剂量",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-M2",
                    required_action="approve",
                ),
            ),
        ]
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    return ctx


def _high_finance_ctx() -> ProjectContext:
    """HIGH-risk: financial loan approval system (no automation/sensitive/low-scope triggers)."""
    ctx = ProjectContext(
        research_target="金融贷款审批系统",
        domain="金融 / 贷款 / 合规",
        goal="审批贷款申请风险",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-F1",
                category="交易欺诈",
                description="欺诈交易未识别导致资金损失",
                severity="high",
            ),
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-fraud",
                stage_name="欺诈检测",
                model_assigned="llm",
                human_action="approve",
                check_criteria="检测准确",
                failure_modes_addressed=["FM-F1"],
                prompt_template="检测欺诈",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-F1",
                    required_action="approve",
                ),
            ),
        ]
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    return ctx


def _medium_team_ctx() -> ProjectContext:
    """MEDIUM-risk: team task management."""
    ctx = ProjectContext(
        research_target="团队任务管理系统",
        domain="项目管理 / 团队协作",
        goal="管理团队任务分配和进度跟踪",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-T1",
                category="任务遗漏",
                description="任务分配遗漏导致延期",
                severity="high",
            ),
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-assign",
                stage_name="任务分配",
                model_assigned="llm",
                human_action="review",
                check_criteria="分配合理",
                failure_modes_addressed=["FM-T1"],
                prompt_template="分配任务",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-T1",
                    required_action="approve",
                ),
            ),
        ]
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    return ctx


def _low_reading_ctx() -> ProjectContext:
    """LOW-risk: personal reading planner."""
    ctx = ProjectContext(
        research_target="个人读书与学习计划管理系统",
        domain="个人学习 / 读书计划 / 本地使用",
        goal="帮助个人制定和跟踪阅读计划",
        current_state=SessionState.S3_REVIEW,
    )
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-1",
                category="目标偏移",
                description="学习计划混乱",
                severity="high",
            ),
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N-plan",
                stage_name="计划生成",
                model_assigned="llm",
                human_action="review",
                check_criteria="计划合理",
                failure_modes_addressed=["FM-1"],
                prompt_template="生成阅读计划",
                oversight_policy=HumanOversightPolicy(
                    stage_id=2,
                    risk_level="high",
                    trigger_reason="FM-1",
                    required_action="approve",
                ),
            ),
        ]
    )
    ctx.stage_3_output = Stage3Output(overall_passed=True)
    return ctx


# ─────────────────────────────────────────────
# 1. CRITICAL 场景：产出 expert_review blocker + 创建 escalate 动作
# ─────────────────────────────────────────────


def test_critical_produces_expert_review_blocker(sqlite_store):
    ctx = _critical_medication_ctx()
    profile = build_stage3_gate_profile(ctx)
    assert profile.risk_tier == ProjectGateRiskTier.CRITICAL
    assert profile.require_expert_review is True

    result = evaluate_stage_gate(ctx, 3)

    expert_blockers = [b for b in result.blockers if b.rule_id == "expert_review"]
    assert len(expert_blockers) == 1, "CRITICAL 场景必须产出 expert_review blocker"
    blocker = expert_blockers[0]
    assert blocker.blocker_type == "expert_review"
    assert blocker.severity == "critical"
    assert blocker.required_resolution == "approve_expert_review"
    assert blocker.source_type == "expert_review"
    assert blocker.source_id == "critical_tier_review"

    # 创建了恰好 1 个 escalate 动作
    expert_actions = [
        a
        for a in ctx.pending_actions
        if a.source_type == "expert_review" and a.source_id == "critical_tier_review"
    ]
    assert len(expert_actions) == 1
    action = expert_actions[0]
    assert action.action_type == "escalate"
    assert action.risk_level == "critical"
    assert action.blocking is True
    assert action.status == "pending"
    # blocker 引用该动作
    assert blocker.action_id == action.action_id


# ─────────────────────────────────────────────
# 2. 幂等：再次评估不重复创建动作
# ─────────────────────────────────────────────


def test_expert_review_idempotent(sqlite_store):
    ctx = _critical_medication_ctx()

    result1 = evaluate_stage_gate(ctx, 3)
    action_id_1 = next(b.action_id for b in result1.blockers if b.rule_id == "expert_review")
    actions_after_first = [
        a
        for a in ctx.pending_actions
        if a.source_type == "expert_review" and a.source_id == "critical_tier_review"
    ]
    assert len(actions_after_first) == 1

    result2 = evaluate_stage_gate(ctx, 3)
    actions_after_second = [
        a
        for a in ctx.pending_actions
        if a.source_type == "expert_review" and a.source_id == "critical_tier_review"
    ]
    assert len(actions_after_second) == 1, "再次评估不得重复创建动作"

    action_id_2 = next(b.action_id for b in result2.blockers if b.rule_id == "expert_review")
    assert action_id_1 == action_id_2, "幂等：引用既有 action_id"


# ─────────────────────────────────────────────
# 3. 动作 approved 后不再阻断
# ─────────────────────────────────────────────


def test_expert_review_approved_unblocks(sqlite_store):
    ctx = _critical_medication_ctx()

    # 首次评估创建动作
    result1 = evaluate_stage_gate(ctx, 3)
    assert any(b.rule_id == "expert_review" for b in result1.blockers)

    action = next(
        a
        for a in ctx.pending_actions
        if a.source_type == "expert_review" and a.source_id == "critical_tier_review"
    )
    # 模拟专家批准
    action.status = "resolved"
    action.reviewer_decision = "approve"

    result2 = evaluate_stage_gate(ctx, 3)
    assert not any(b.rule_id == "expert_review" for b in result2.blockers), (
        "已批准后不得再产出 expert_review blocker"
    )


# ─────────────────────────────────────────────
# 4. HIGH/MEDIUM/LOW 场景：无 expert_review blocker
# ─────────────────────────────────────────────


def test_high_risk_no_expert_review_blocker(sqlite_store):
    ctx = _high_finance_ctx()
    profile = build_stage3_gate_profile(ctx)
    assert profile.risk_tier == ProjectGateRiskTier.HIGH
    assert profile.require_expert_review is False

    result = evaluate_stage_gate(ctx, 3)
    assert not any(b.rule_id == "expert_review" for b in result.blockers)


def test_medium_risk_no_expert_review_blocker(sqlite_store):
    ctx = _medium_team_ctx()
    profile = build_stage3_gate_profile(ctx)
    assert profile.require_expert_review is False

    result = evaluate_stage_gate(ctx, 3)
    assert not any(b.rule_id == "expert_review" for b in result.blockers)


def test_low_risk_no_expert_review_blocker(sqlite_store):
    ctx = _low_reading_ctx()
    profile = build_stage3_gate_profile(ctx)
    assert profile.require_expert_review is False

    result = evaluate_stage_gate(ctx, 3)
    assert not any(b.rule_id == "expert_review" for b in result.blockers)


# ─────────────────────────────────────────────
# 5. GATE_RULES_DISABLED="redteam_coverage" → 跳过（detailed 报告显示 skipped）
# ─────────────────────────────────────────────


def test_disable_redteam_coverage_shows_skipped(sqlite_store, monkeypatch):
    monkeypatch.setattr(settings, "gate_rules_disabled", "redteam_coverage")
    ctx = _critical_medication_ctx()

    result = evaluate_stage_gate(ctx, 3, detailed=True)
    report = result.__dict__["report"]
    assert report is not None

    redteam_record = next(r for r in report.rules if r.rule_id == "redteam_coverage")
    assert redteam_record.status == "skipped"
    assert "disabled" in (redteam_record.skipped_reason or "").lower()

    # redteam 不在阻断列表
    assert not any(b.rule_id == "redteam_coverage" for b in result.blockers)
    # 安全底线规则仍评估（expert_review 本身是安全底线，仍产出 blocker）
    assert any(b.rule_id == "expert_review" for b in result.blockers)


# ─────────────────────────────────────────────
# 6. GATE_RULES_DISABLED="missing_output" → 仍评估（安全底线忽略禁用）
# ─────────────────────────────────────────────


def test_disable_safety_bottom_line_ignored(sqlite_store, monkeypatch):
    """missing_output 是安全底线规则，配置禁用也忽略。"""
    monkeypatch.setattr(settings, "gate_rules_disabled", "missing_output")
    assert is_safety_bottom_line("missing_output") is True

    ctx = ProjectContext()
    ctx.session_id = "sess-disable-safety"
    ctx.tenant_id = "tenant-disable"

    result = evaluate_stage_gate(ctx, 1, detailed=True)
    report = result.__dict__["report"]
    assert report is not None

    # missing_output 仍阻断（未跳过）
    missing_output_blockers = [b for b in result.blockers if b.rule_id == "missing_output"]
    assert len(missing_output_blockers) > 0, "安全底线规则配置禁用也必须评估"

    mo_record = next(r for r in report.rules if r.rule_id == "missing_output")
    assert mo_record.status == "blocked", "安全底线规则不得显示为 skipped"


# ─────────────────────────────────────────────
# 7. registered_rules() 返回 13 条（含 expert_review）
# ─────────────────────────────────────────────


def test_registered_rules_count_is_thirteen():
    rules = registered_rules()
    assert len(rules) == 13
    rule_ids = {r.rule_id for r in rules}
    assert "expert_review" in rule_ids


# ─────────────────────────────────────────────
# 8. manifest 完整性：13 条双向匹配
# ─────────────────────────────────────────────


def test_manifest_bidirectional_integrity():
    implemented = {r.rule_id for r in registered_rules()}
    manifest_ids = set(RULE_MANIFEST.keys())
    assert implemented == manifest_ids, (
        f"missing in manifest: {sorted(implemented - manifest_ids)}; "
        f"missing impl: {sorted(manifest_ids - implemented)}"
    )
    assert len(implemented) == 13


def test_expert_review_is_safety_bottom_line():
    assert is_safety_bottom_line("expert_review") is True
