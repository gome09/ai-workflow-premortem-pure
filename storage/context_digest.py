# storage/context_digest.py
"""ProjectContext 内容指纹：用于 save() 跳过无变化的大字段重写。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# 每次 save 都会刷新 updated_at；该值只落 sessions 列，不属于内容体。
_VOLATILE_FIELDS = frozenset({"updated_at"})


def compute_context_digest(data: dict[str, Any]) -> str:
    """对去除易变字段后的上下文做规范化 JSON 哈希（加密前计算）。

    必须在字段加密前调用：Fernet 每次加密的密文不同，用密文做指纹会让
    指纹永远变化，失去“内容未变则跳过重写”的意义。
    """
    payload = {key: value for key, value in data.items() if key not in _VOLATILE_FIELDS}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
