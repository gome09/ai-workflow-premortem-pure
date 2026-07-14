# tools/prompt_injection_scanner.py
from __future__ import annotations

import re
from typing import Literal

# 注入类：试图覆盖/绕过指令
INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior) instructions",
    r"disregard (all )?(previous|prior) instructions",
    r"developer message",
    r"忽略(以上|之前|所有).*指令",
    r"绕过.*(审核|人工|安全)",
]

# 泄露类：试图诱导系统吐出系统提示词/初始指令（LLM07）
LEAKAGE_PATTERNS = [
    r"system prompt",
    r"泄露.*(系统提示词|system prompt)",
    r"repeat (your|the) (system|initial) (prompt|instructions)",
    r"输出你的(系统提示|初始指令)",
    r"reveal (your|the) (system|initial) (prompt|instructions)",
    r"what (is|are|'s) your (system|initial) (prompt|instructions)",
    r"show me your (system|initial) (prompt|instructions)",
]


def classify_injection(text: str) -> Literal["injection", "leakage"] | None:
    """返回命中类别：injection / leakage / None。

    injection 优先于 leakage（同一段文本既绕过又泄露时，按注入处置）。
    """
    haystack = text or ""
    if any(re.search(p, haystack, flags=re.IGNORECASE | re.S) for p in INJECTION_PATTERNS):
        return "injection"
    if any(re.search(p, haystack, flags=re.IGNORECASE | re.S) for p in LEAKAGE_PATTERNS):
        return "leakage"
    return None


def has_prompt_injection(text: str) -> bool:
    """向后兼容签名：命中任一类别即 True。"""
    return classify_injection(text) is not None
