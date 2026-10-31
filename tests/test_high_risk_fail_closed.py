# tests/test_high_risk_fail_closed.py
"""Milestone 1 P4: HIGH/CRITICAL 场景必须 fail-closed。

验收：
- HIGH/CRITICAL 下 Markdown 回退必须保留 parser_errors（不允许弱 fallback 通过），
  readiness 产出 high severity 的 parser_error blocker，并带 requires_structured_output。
- 低风险场景保持原有 Markdown 回退行为，不产生 parser error。
- strict 模式下缺少明确监督信号的节点不得被推断出 HumanOversightPolicy，
  且 policy gap 必须生成 blocking edit 动作。
- Gate 规则异常转为确定性 gate_rule_error critical blocker。
- HIGH/CRITICAL 的 Gate 评估落表失败 → GateDataError → readiness gate_data_error
  + retry_gate_persistence 阻断；非高风险会话保持原降级行为。
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from core.gates.engine import GateDataError, evaluate_stage_gate
from core.gates.risk_profile import (
    ProjectGateRiskTier,
    classify_project_risk,
    requires_strict_structured_output,
)
from core.models import FailureMode, ProjectContext, SessionState, Stage1Output
from core.oversight_service import create_actions_from_policy_gaps
from core.stage_readiness_service import build_stage_readiness
from stages.stage_1_failure_mode import Stage1Executor
from stages.stage_2_workflow_design import Stage2Executor, infer_oversight_policy
from storage.backends.sqlite_store import SQLiteSessionStore

MARKDOWN_STAGE1 = """
| 失败模式ID | 类别 | 具体描述 | 严重程度 | 依据来源 |
|-----------|------|----------|----------|----------|
| FM-001 | 幻觉 | 虚构法律条文编号 | high | 多份评测报告 |
"""

MARKDOWN_STAGE2 = """
| 节点ID | 阶段名称 | 分配模型/模式 | 人工动作 | 检查标准 | 覆盖的失败模式ID |
|--------|----------|--------------|----------|----------|----------------|
| N-01 | 文书初稿生成 | GPT-4o | 人工复核输出 | 格式符合模板 | FM-001 |
"""


# ── fixtures / helpers ───────────────────────────────────────────────
@pytest.fixture
def gate_store(tmp_path, monkeypatch):
    """隔离的 SQLite store，替换全局 session_store（Gate 旁路落表依赖它）。"""
    store = SQLiteSessionStore(db_path=str(tmp_path / "high_risk.db"))
    store.initialize()
    monkeypatch.setattr("storage.session_store.session_store", store)
    return store


def _risky_ctx(tier: str) -> ProjectContext:
    if tier == "high":
        ctx = ProjectContext(
            tenant_id="tenant-a",
            research_target="GPT-4o",
            domain="法律文书生成",
            goal="提高合同起草准确率",
        )
    else:
        ctx = ProjectContext(
            tenant_id="tenant-a",
            research_target="临床用药助手",
            domain="患者数据审核",
            goal="降低处方错误",
        )
    ctx.current_state = SessionState.S1_RUNNING
    return ctx


def _low_risk_ctx() -> ProjectContext:
    ctx = ProjectContext(
        tenant_id="tenant-a",
        research_target="个人日记整理助手",
        domain="个人生活笔记",
        goal="整理日记内容",
    )
    ctx.current_state = SessionState.S1_RUNNING
    return ctx


# ── 1. 解析失败在 HIGH/CRITICAL 下保持阻断语义 ───────────────────────
@pytest.mark.parametrize("tier", ["high", "critical"])
def test_markdown_fallback_is_rejected_for_high_risk(tier, gate_store):
    ctx = _risky_ctx(tier)
    expected_tier = ProjectGateRiskTier.HIGH if tier == "high" else ProjectGateRiskTier.CRITICAL
    assert classify_project_risk(ctx)[0] == expected_tier
    assert requires_strict_structured_output(ctx) is True
    gate_store.save(ctx)

    updated = Stage1Executor().parse_output(MARKDOWN_STAGE1, ctx)

    # 回退仍产出内容，便于人工修数据，但不能被当作"结构化输出通过"。
    assert updated.stage_1_output is not None
    assert updated.stage_1_output.failure_modes
    assert updated.parser_errors["stage_1"] == "structured_output_required_for_high_risk"

    readiness = build_stage_readiness(updated)["stage_1"]
    parser_blockers = [
        blocker for blocker in readiness["blockers"] if blocker["blocker_type"] == "parser_error"
    ]
    assert parser_blockers, readiness
    assert parser_blockers[0]["severity"] == "high"
    assert parser_blockers[0]["metadata"]["requires_structured_output"] is True
    assert readiness["can_continue"] is False


def test_markdown_fallback_stays_permissive_for_low_risk():
    ctx = _low_risk_ctx()
    assert classify_project_risk(ctx)[0] == ProjectGateRiskTier.LOW
    assert requires_strict_structured_output(ctx) is False

    updated = Stage1Executor().parse_output(MARKDOWN_STAGE1, ctx)

    assert updated.stage_1_output is not None
    assert updated.stage_1_output.failure_modes
    assert "stage_1" not in updated.parser_errors


# ── 2. 监督策略推断：strict 不接受默认 policy ────────────────────────
def test_strict_oversight_policy_refuses_implicit_default():
    from core.models import WorkflowNode

    node = WorkflowNode(
        node_id="N-01",
        stage_name="初稿生成",
        model_assigned="GPT-4o",
        human_action="人工复核输出",
        check_criteria="格式符合模板",
        failure_modes_addressed=["FM-001"],
        prompt_template="生成初稿",
    )

    assert infer_oversight_policy(node, strict=True) is None
    # 非 strict 保持既有兼容行为。
    assert infer_oversight_policy(node, strict=False) is not None


def test_strict_oversight_policy_accepts_explicit_signal():
    from core.models import WorkflowNode

    node = WorkflowNode(
        node_id="N-01",
        stage_name="初稿生成",
        model_assigned="GPT-4o",
        human_action="逐条核验证据来源",
        check_criteria="引用可验证",
        failure_modes_addressed=["FM-001"],
        prompt_template="生成初稿",
    )

    policy = infer_oversight_policy(node, strict=True)
    assert policy is not None
    assert policy.required_action == "verify_evidence"


# ── 3. Stage2 strict：Markdown 回退 + policy gap 阻断 ────────────────
def test_high_risk_stage2_policy_gap_creates_blocking_edit_action(gate_store):
    ctx = _risky_ctx("high")
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="虚构不存在的法律条文",
                severity="high",
                evidence="多份测试报告记录",
            )
        ]
    )
    ctx.current_state = SessionState.S2_RUNNING
    gate_store.save(ctx)

    updated = Stage2Executor().parse_output(MARKDOWN_STAGE2, ctx)

    node = updated.stage_2_output.workflow_nodes[0]
    assert node.oversight_policy is None
    assert updated.parser_errors["stage_2"] == "structured_output_required_for_high_risk"

    actions = create_actions_from_policy_gaps(updated, 2)
    assert len(actions) == 1
    action = actions[0]
    assert action.source_type == "policy_gap"
    assert action.action_type == "edit"
    assert action.blocking is True
    assert action.risk_level == "high"

    readiness = build_stage_readiness(updated)["stage_2"]
    policy_blockers = [
        blocker for blocker in readiness["blockers"] if blocker["blocker_type"] == "policy_gap"
    ]
    assert policy_blockers, readiness
    assert readiness["can_continue"] is False


# ── 4. Gate 规则异常确定性阻断 ──────────────────────────────────────
def test_gate_rule_exception_becomes_deterministic_blocker(gate_store, monkeypatch):
    ctx = _risky_ctx("high")
    gate_store.save(ctx)

    def boom(_ctx, _stage):
        raise RuntimeError("rule crashed")

    monkeypatch.setattr("core.gates.rules.missing_output.rule.evaluate", boom)

    result = evaluate_stage_gate(ctx, 1)

    assert result.can_continue is False
    blocker = next(b for b in result.blockers if b.blocker_type == "gate_rule_error")
    assert blocker.severity == "critical"
    assert blocker.rule_id == "missing_output"
    assert blocker.can_be_overridden_by_approval is False
    assert blocker.required_resolution == "rerun_stage"


# ── 5. Gate 落表失败：HIGH 阻断，非高风险保持降级 ────────────────────
@pytest.mark.parametrize("tier", ["high", "critical"])
def test_high_risk_gate_persistence_failure_blocks(tier, gate_store, monkeypatch):
    ctx = _risky_ctx(tier)
    gate_store.save(ctx)
    monkeypatch.setattr(
        gate_store,
        "record_gate_evaluation",
        Mock(side_effect=RuntimeError("database is down")),
    )

    with pytest.raises(GateDataError):
        evaluate_stage_gate(ctx, 1)

    readiness = build_stage_readiness(ctx)
    stage_1 = readiness["stage_1"]
    assert stage_1["can_continue"] is False
    data_blockers = [
        blocker for blocker in stage_1["blockers"] if blocker["blocker_type"] == "gate_data_error"
    ]
    assert data_blockers, stage_1
    assert data_blockers[0]["severity"] == "critical"
    assert data_blockers[0]["required_resolution"] == "retry_gate_persistence"
    # stage 4 摘要同样不能被 Gate 落表失败打成 500。
    assert (
        readiness["stage_4"]["stage_metadata"]["final_governance_summary"]["report_export_allowed"]
        is False
    )


def test_low_risk_gate_persistence_failure_stays_non_blocking(gate_store, monkeypatch):
    ctx = _low_risk_ctx()
    gate_store.save(ctx)
    monkeypatch.setattr(
        gate_store,
        "record_gate_evaluation",
        Mock(side_effect=RuntimeError("database is down")),
    )

    # 非高风险会话：治理数据缺一行可接受，评估本身不能被卡死。
    result = evaluate_stage_gate(ctx, 1)

    assert result.can_continue is False  # missing_stage_output 仍阻断
    assert all(b.blocker_type != "gate_data_error" for b in result.blockers)
