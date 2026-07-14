"""T1.5 回归测试：报告 AI 生成内容标识补强。"""

from core.models import ProjectContext
from core.report_service import build_markdown_report, build_report_dict


def _build_minimal_ctx() -> ProjectContext:
    return ProjectContext(
        research_target="测试项目",
        domain="测试",
        goal="验证 AI 标识",
    )


def test_json_report_has_ai_generated_notice():
    report = build_report_dict(_build_minimal_ctx())
    assert "ai_generated_notice" in report
    notice = report["ai_generated_notice"]
    assert "zh" in notice
    assert "en" in notice
    assert "basis" in notice
    assert "《人工智能生成合成内容标识办法》" in notice["zh"]


def test_json_report_keeps_disclaimer_backward_compat():
    report = build_report_dict(_build_minimal_ctx())
    assert "disclaimer" in report
    assert "AI-generated outputs must be reviewed" in report["disclaimer"]


def test_markdown_report_has_chinese_ai_notice_in_first_10_lines():
    md = build_markdown_report(_build_minimal_ctx())
    lines = md.split("\n")[:10]
    joined = "\n".join(lines)
    assert "本报告由 AI 辅助生成" in joined


def test_markdown_report_has_html_ai_comment():
    md = build_markdown_report(_build_minimal_ctx())
    assert "<!-- ai-generated: true" in md
