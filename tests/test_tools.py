# tests/test_tools.py
from __future__ import annotations

import pytest

from core.context_manager import parse_review_action
from tools.flag_extractor import extract_flags


class TestFlagExtractor:
    def test_extract_chinese_bracket(self):
        text = "这个数据来源【需核验】，可能不准确。"
        flags = extract_flags(text, stage=1)
        assert len(flags) == 1
        assert flags[0].stage == 1
        assert "数据来源" in flags[0].content

    def test_extract_square_bracket(self):
        text = "该功能[需核验]是否在新版本中仍然有效。"
        flags = extract_flags(text, stage=2)
        assert len(flags) == 1

    def test_extract_multiple_flags(self):
        text = """
        - 模型在该场景下准确率约 85%【需核验】
        - 上下文窗口限制为 128k【需核验】
        - 响应延迟约 2 秒（已验证）
        """
        flags = extract_flags(text, stage=1)
        assert len(flags) == 2

    def test_no_flags(self):
        text = "这段文字不包含任何需要核验的内容。"
        flags = extract_flags(text, stage=1)
        assert len(flags) == 0

    def test_flag_with_context(self):
        text = "上一行\n该数据【需核验】\n下一行"
        flags = extract_flags(text, stage=1)
        assert len(flags) == 1
        assert "上一行" in flags[0].context or "下一行" in flags[0].context


class TestParseReviewAction:
    @pytest.mark.parametrize(
        "input_text,expected_action",
        [
            ("确认", "approve"),
            ("approve", "approve"),
            ("ok", "approve"),
            ("好", "approve"),
            ("没问题", "approve"),
            ("通过", "approve"),
        ],
    )
    def test_approve_keywords(self, input_text, expected_action):
        action, _ = parse_review_action(input_text)
        assert action == expected_action

    @pytest.mark.parametrize(
        "input_text,expected_action",
        [
            ("回退", "back"),
            ("back", "back"),
            ("返回", "back"),
            ("上一步", "back"),
        ],
    )
    def test_back_keywords(self, input_text, expected_action):
        action, _ = parse_review_action(input_text)
        assert action == expected_action

    def test_back_to_design(self):
        action, _ = parse_review_action("回退工作流")
        assert action == "back_to_design"

    def test_revise_with_content(self):
        action, extra = parse_review_action("修改：阶段一漏掉了上下文遗忘这个失败模式")
        assert action == "revise"
        assert "上下文遗忘" in extra

    def test_long_input_treated_as_revise(self):
        """超过10字符的非关键词输入，默认视为修改意见"""
        action, _ = parse_review_action(
            "我觉得这里的失败模式分析不够深入，需要增加对长文本场景的分析"
        )
        assert action == "revise"

    def test_unknown_short_input(self):
        action, _ = parse_review_action("嗯")
        assert action == "unknown"
