# tests/test_models.py
from __future__ import annotations

from core.models import (
    FlaggedItem,
    FlagStatus,
    Message,
    MessageRole,
    ProjectContext,
    SessionState,
)


class TestProjectContext:
    def test_create_default(self):
        ctx = ProjectContext()
        assert ctx.session_id != ""
        assert ctx.current_state == SessionState.INIT
        assert ctx.research_target == ""
        assert ctx.iteration_count == 0

    def test_append_message(self, base_ctx):
        msg = Message(role=MessageRole.USER, content="测试消息")
        base_ctx.append_message(1, msg)

        history = base_ctx.get_stage_history(1)
        assert len(history) == 1
        assert history[0].content == "测试消息"

    def test_append_message_multiple_stages(self, base_ctx):
        base_ctx.append_message(1, Message(role=MessageRole.USER, content="阶段一消息"))
        base_ctx.append_message(2, Message(role=MessageRole.USER, content="阶段二消息"))

        assert len(base_ctx.get_stage_history(1)) == 1
        assert len(base_ctx.get_stage_history(2)) == 1
        assert len(base_ctx.get_stage_history(3)) == 0

    def test_get_pending_flags(self, base_ctx):
        base_ctx.flagged_items = [
            FlaggedItem(stage=1, content="待核验项A", status=FlagStatus.PENDING),
            FlaggedItem(stage=1, content="已核验项B", status=FlagStatus.VERIFIED),
            FlaggedItem(stage=2, content="待核验项C", status=FlagStatus.PENDING),
        ]
        pending = base_ctx.get_pending_flags()
        assert len(pending) == 2
        assert all(f.status == FlagStatus.PENDING for f in pending)

    def test_context_summary_empty(self, base_ctx):
        summary = base_ctx.to_context_summary()
        assert "GPT-4o" in summary
        assert "法律文书生成" in summary
        assert "提高合同起草准确率" in summary

    def test_context_summary_with_stage1(self, ctx_with_stage1):
        summary = ctx_with_stage1.to_context_summary()
        # context summary should preserve failure-mode ids for audit traceability
        assert "FM-001" in summary
        assert "幻觉" in summary
        assert "HIGH" in summary

    def test_serialization_roundtrip(self, ctx_with_stage1):
        """序列化后反序列化，数据应保持一致"""
        json_str = ctx_with_stage1.model_dump_json()
        restored = ProjectContext.model_validate_json(json_str)

        assert restored.session_id == ctx_with_stage1.session_id
        assert restored.research_target == ctx_with_stage1.research_target
        assert restored.stage_1_output is not None
        assert len(restored.stage_1_output.failure_modes) == 2
        assert restored.stage_1_output.failure_modes[0].id == "FM-001"
