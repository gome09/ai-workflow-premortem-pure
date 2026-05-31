# tools/prompt_injection_scanner.py
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior) instructions",
    r"disregard (all )?(previous|prior) instructions",
    r"system prompt",
    r"developer message",
    r"忽略(以上|之前|所有).*指令",
    r"泄露.*(系统提示词|system prompt)",
    r"绕过.*(审核|人工|安全)",
]


def has_prompt_injection(text: str) -> bool:
    haystack = text or ""
    return any(
        re.search(pattern, haystack, flags=re.IGNORECASE | re.S) for pattern in INJECTION_PATTERNS
    )
