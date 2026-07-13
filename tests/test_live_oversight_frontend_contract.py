# tests/test_live_oversight_frontend_contract.py
"""前后端「实时人工监督占位」契约测试。

前端 app.py 在 import 时会执行 Streamlit UI 代码，不便直接单测；因此这里只校验
两处纯粹、可导入的契约点：
  1) 前端 labels.ACTION_SOURCE_ZH 覆盖后端会产生的所有 action source_type；
  2) 前端用于识别标记的正则，能匹配后端 graph.nodes.live_oversight_marker 的输出。

只要这两点成立，前端渲染器就能把标记原位展开为与左侧面板一致的实时摘要。
"""
from __future__ import annotations

import os
import re
import sys

# 让 `import labels` 生效（前端模块以扁平方式互相 import）。
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))

import labels  # noqa: E402

from core.oversight_service import _ACTION_SOURCE_LABEL  # noqa: E402
from graph.nodes import live_oversight_marker  # noqa: E402

# 与 frontend/app.py::LIVE_OVERSIGHT_RE 保持一致。
_FRONTEND_MARKER_RE = re.compile(r"\[\[LIVE_OVERSIGHT(?:\s+stage=(\d+))?\]\]")


def test_frontend_labels_cover_backend_action_sources():
    missing = sorted(set(_ACTION_SOURCE_LABEL) - set(labels.ACTION_SOURCE_ZH))
    assert not missing, f"前端 ACTION_SOURCE_ZH 缺少后端来源标签：{missing}"


def test_action_source_zh_has_safe_default():
    # 未知来源不应丢信息或报错，而是回退到通用中文。
    assert labels.action_source_zh("some_new_source_type") == "有事项需要人工处理"


def test_frontend_regex_matches_backend_marker():
    for stage in (1, 2, 3, 4):
        marker = live_oversight_marker(stage)
        match = _FRONTEND_MARKER_RE.search(marker)
        assert match is not None, f"前端正则无法匹配后端标记：{marker!r}"
        assert match.group(1) == str(stage)


def test_marker_extraction_splits_surrounding_text():
    """标记可嵌在文本中间，渲染器据此切成 前文 / 实时摘要 / 后文。"""
    content = f"阶段一分析已完成。\n{live_oversight_marker(1)}\n请确认继续。"
    match = _FRONTEND_MARKER_RE.search(content)
    assert match is not None
    before = content[: match.start()].rstrip()
    after = content[match.end() :].strip()
    assert before == "阶段一分析已完成。"
    assert after == "请确认继续。"
    assert match.group(1) == "1"
