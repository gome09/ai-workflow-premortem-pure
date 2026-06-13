# tests/test_stage1_evidence_unhashable_fix.py
"""Regression test: _prepare_materials should not crash with unhashable EvidenceSource.

This test verifies the fix for the bug where dict.fromkeys() was used on
EvidenceSource objects (which are unhashable Pydantic BaseModel instances).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.models import ProjectContext, SessionState
from stages.stage_1_failure_mode import Stage1Executor


@pytest.fixture
def ctx_for_stage1() -> ProjectContext:
    """Context ready for Stage 1 execution."""
    ctx = ProjectContext()
    ctx.research_target = "AI辅助药物管理系统"
    ctx.domain = "门诊、慢病管理、居家用药场景"
    ctx.goal = "用药信息整理和风险预警"
    ctx.current_state = SessionState.S1_RUNNING
    ctx.user_materials = [
        "系统只作为立项前风险分析工具使用",
        "重点关注药物名称混淆等失败模式",
        "任何涉及停药换药的建议必须人工审核",
    ]
    return ctx


@pytest.fixture
def mock_search_results_with_urls():
    """Mock Tavily search results with real-looking URLs."""
    from tools.search import SearchResult

    return [
        SearchResult(
            title="药物管理系统安全分析",
            url="https://example.com/medication-safety",
            content="AI辅助药物管理存在多种失败模式...",
            score=0.92,
        ),
        SearchResult(
            title="医疗AI幻觉问题研究",
            url="https://example.com/medical-ai-hallucination",
            content="大模型在医疗场景中的幻觉风险...",
            score=0.87,
        ),
    ]


class TestStage1EvidenceUnhashableFix:
    """Regression tests for the unhashable EvidenceSource fix."""

    def test_prepare_materials_with_search_and_user_evidence(
        self, ctx_for_stage1, mock_search_results_with_urls
    ):
        """_prepare_materials must not crash when both search results and user materials exist.

        Before the fix, this would raise:
            TypeError: unhashable type: 'EvidenceSource'
        because dict.fromkeys() was used on EvidenceSource objects.
        """
        executor = Stage1Executor()

        with (
            patch.object(executor, "stage_id", 1),
            patch(
                "stages.stage_1_failure_mode.research_tool.search",
                return_value=mock_search_results_with_urls,
            ),
        ):
            # This should NOT raise TypeError
            materials_text = executor._prepare_materials(ctx_for_stage1)

        # Verify materials text was generated
        assert materials_text is not None
        assert len(materials_text) > 0

        # Verify evidence was collected
        assert len(ctx_for_stage1.evidence_sources) > 0

        # Verify both search results and user materials are present
        source_types = {ev.source_type for ev in ctx_for_stage1.evidence_sources}
        assert "user_material" in source_types

    def test_prepare_materials_with_user_evidence_only(self, ctx_for_stage1):
        """_prepare_materials works when search returns empty results."""
        executor = Stage1Executor()

        with (
            patch.object(executor, "stage_id", 1),
            patch(
                "stages.stage_1_failure_mode.research_tool.search",
                return_value=[],
            ),
        ):
            materials_text = executor._prepare_materials(ctx_for_stage1)

        assert materials_text is not None
        # User materials should still be present
        assert len(ctx_for_stage1.evidence_sources) == len(ctx_for_stage1.user_materials)

    def test_prepare_materials_idempotent(self, ctx_for_stage1, mock_search_results_with_urls):
        """Calling _prepare_materials twice should not duplicate evidence."""
        executor = Stage1Executor()

        with (
            patch.object(executor, "stage_id", 1),
            patch(
                "stages.stage_1_failure_mode.research_tool.search",
                return_value=mock_search_results_with_urls,
            ),
        ):
            executor._prepare_materials(ctx_for_stage1)
            first_count = len(ctx_for_stage1.evidence_sources)

            # Second call should reuse cached evidence (search_sources already set)
            executor._prepare_materials(ctx_for_stage1)
            second_count = len(ctx_for_stage1.evidence_sources)

        assert first_count == second_count
