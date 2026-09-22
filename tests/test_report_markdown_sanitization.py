# tests/test_report_markdown_sanitization.py
"""报告 Markdown 导出净化测试（2026-09-01 修复：导出此前无转义）。

背景：build_markdown_report 以 f-string 直接拼接 LLM 生成内容，导出报告被
下游渲染器直接渲染时 `<script>` / `[x](javascript:...)` 可执行
（STATE.md Blockers 登记项）。修复采用出口收敛：_sanitize_markdown 在
build_markdown_report 返回点统一净化。
"""

from __future__ import annotations

from core.models import ProjectContext, SessionState
from core.report_service import (
    _sanitize_markdown,
    build_markdown_report,
    create_report_artifact,
)


def _ctx_with(target: str) -> ProjectContext:
    return ProjectContext(
        research_target=target,
        domain="测试",
        goal="验证报告净化",
        current_state=SessionState.S4_REVIEW,
    )


def test_sanitize_escapes_html_tags():
    out = _sanitize_markdown("描述：<script>alert(1)</script> 结束")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "alert(1)" in out  # 文本内容保留


def test_sanitize_neutralizes_pseudo_protocol_links():
    out = _sanitize_markdown("点[这里](javascript:alert(1))查看")
    assert "](javascript:" not in out
    assert "](blocked:" in out
    out2 = _sanitize_markdown("链接 [x](JavaScript:xx) 与 [y](vbscript:z) 与 [d](data:text/html,x)")
    assert "javascript" not in out2.lower().replace("blocked", "")
    assert "vbscript" not in out2.lower().replace("blocked", "")
    assert "data:" not in out2


def test_sanitize_keeps_fenced_code_block_verbatim():
    text = '前文\n```json\n{"a": "<b>&x"}\n```\n后文'
    out = _sanitize_markdown(text)
    # 块内保留原样（维持 JSON 可复制性）
    assert '{"a": "<b>&x"}' in out
    # 块外不受影响（无危险字符时原样）
    assert "前文" in out and "后文" in out


def test_sanitize_preserves_aigc_comment():
    text = "<!-- ai-generated: true; generator: ai-workflow-premortem; version: 0.3.0 -->"
    out = _sanitize_markdown(text)
    assert out == text  # 静态标识注释原样保留


def test_sanitize_escapes_ampersand():
    out = _sanitize_markdown("A & B")
    assert out == "A &amp; B"


def test_full_report_escapes_llm_content():
    """端到端：含注入向量的 LLM 描述进入报告后不得出现裸 script 标签。"""
    ctx = _ctx_with("理财助手<script>fetch('evil')</script>")
    report = build_markdown_report(ctx)
    assert "<script>" not in report
    assert "fetch('evil')" in report  # 文本仍在，仅标签形式被转义


def test_full_report_keeps_aigc_comment():
    ctx = _ctx_with("普通目标")
    report = build_markdown_report(ctx)
    assert "<!-- ai-generated: true" in report


def test_report_artifact_markdown_is_sanitized():
    ctx = _ctx_with("目标 [链接](javascript:alert(1))")
    artifact = create_report_artifact(ctx)
    assert "](javascript:" not in artifact.content_markdown
