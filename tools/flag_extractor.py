# tools/flag_extractor.py
from __future__ import annotations

import re

from core.models import FlaggedItem


def extract_flags(text: str, stage: int) -> list[FlaggedItem]:
    """
    从 AI 输出中提取所有【需核验】标注。
    支持的格式：【需核验】、[需核验]、(需核验)
    """
    pattern = r"[【\[\(]需核验[】\]\)]"
    flags = []

    # 按行扫描，提取包含标注的行及其上下文
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            # 取前后各一行作为上下文
            start = max(0, i - 1)
            end = min(len(lines), i + 2)
            context = "\n".join(lines[start:end])

            # 清理标注符号，保留核心内容
            clean_content = re.sub(pattern, "", line).strip()
            clean_content = re.sub(r"^[-•*]\s*", "", clean_content)

            if clean_content:
                flags.append(
                    FlaggedItem(
                        stage=stage,
                        content=clean_content,
                        context=context,
                    )
                )

    return flags
