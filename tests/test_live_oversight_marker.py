# tests/test_live_oversight_marker.py
"""对话区人工监督摘要「实时占位」回归测试。

背景：审核引导语与被阻断提示曾把「N 项待处理监督事项 / 阻断原因」写死进历史
消息（冻结快照），而左侧面板实时重算，处理动作后二者不同步（右 N / 左 0）。

方向 1 修复：助手消息只写入稳定的 LIVE_OVERSIGHT 标记，前端渲染时基于实时
pending_actions / stage_readiness 展开。本测试锁定：
  1) 审核引导语与被阻断提示都不再内联任何动作/阻断的数量或明细；
  2) 只保留稳定的、带 stage 上下文的标记；
  3) 处理（dismiss）动作后，历史消息文本保持不变（不产生快照漂移）。
"""

from __future__ import annotations

import re

from core.models import (
    EvidenceSource,
    FailureMode,
    ProjectContext,
    SessionState,
    Stage1Output,
)
from graph.nodes import _build_review_prompt, live_oversight_marker
from graph.review_gate import apply_review_gate

# 任何形如「N 项待处理的人工监督事项」「共有 N 项需要处理」等旧冻结文案的特征。
_FROZEN_COUNT_PATTERNS = [
    re.compile(r"有\s*\d+\s*项待处理的人工监督事项"),
    re.compile(r"共有\s*\d+\s*项需要处理"),
    re.compile(r"没有待处理的人工监督事项"),
]


def _stage1_ctx_with_actions() -> ProjectContext:
    """构造一个阶段一含高风险失败模式 + 未核验证据的上下文（会产生阻断动作）。"""
    ctx = ProjectContext()
    ctx.research_target = "GPT-4o"
    ctx.domain = "法律文书生成"
    ctx.goal = "提高合同起草准确率"
    ctx.evidence_sources = [
        EvidenceSource(
            evidence_id="EVID-001",
            session_id=ctx.session_id,
            title="未核验来源",
            source_type="forum",
            credibility_score=0.3,
            summary="论坛帖子",
            verified=False,
        )
    ]
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="虚构不存在的法律条文",
                severity="high",
                evidence="测试记录",
                evidence_ids=["EVID-001"],
            )
        ],
        direct_conclusion="存在显著幻觉风险。",
        raw_summary="原始输出...",
    )
    ctx.current_state = SessionState.S1_REVIEW
    return ctx


def test_review_prompt_uses_marker_not_frozen_counts():
    ctx = _stage1_ctx_with_actions()
    apply_review_gate(ctx, stage=1, stage_output_version=1)
    # 前置条件：确有待处理动作，否则测试没有意义。
    assert ctx.get_pending_actions(stage=1), "fixture 应产生阻断动作"

    guide = _build_review_prompt(ctx, stage=1)

    # 含稳定的、带 stage 的标记。
    assert live_oversight_marker(1) in guide
    assert "[[LIVE_OVERSIGHT stage=1]]" in guide

    # 不再内联任何冻结的数量/明细文案。
    for pattern in _FROZEN_COUNT_PATTERNS:
        assert not pattern.search(guide), f"引导语仍内联冻结文案：{pattern.pattern}"


def test_marker_is_stable_across_action_resolution():
    """处理动作前后，历史引导语文本必须完全一致（无快照漂移）。"""
    ctx = _stage1_ctx_with_actions()
    apply_review_gate(ctx, stage=1, stage_output_version=1)

    guide_before = _build_review_prompt(ctx, stage=1)

    # 把所有待处理动作标记为已处理（模拟用户处理）。
    for action in ctx.get_pending_actions(stage=1):
        action.status = "resolved"

    guide_after = _build_review_prompt(ctx, stage=1)

    assert guide_before == guide_after
    # 两个版本都仍只含标记、无冻结计数。
    for guide in (guide_before, guide_after):
        assert live_oversight_marker(1) in guide
        for pattern in _FROZEN_COUNT_PATTERNS:
            assert not pattern.search(guide)


def test_marker_present_even_when_no_actions():
    """无待处理动作时也只放标记，由前端实时决定显示「无监督事项」。"""
    ctx = ProjectContext()
    ctx.research_target = "GPT-4o"
    ctx.domain = "通用"
    ctx.goal = "测试"
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-100",
                category="体验",
                description="低风险问题",
                severity="low",
                evidence="n/a",
            )
        ],
        direct_conclusion="低风险。",
        raw_summary="...",
    )
    ctx.current_state = SessionState.S1_REVIEW
    apply_review_gate(ctx, stage=1, stage_output_version=1)

    guide = _build_review_prompt(ctx, stage=1)
    assert live_oversight_marker(1) in guide
    for pattern in _FROZEN_COUNT_PATTERNS:
        assert not pattern.search(guide)
