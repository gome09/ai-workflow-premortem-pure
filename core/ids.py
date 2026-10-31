# core/ids.py
"""全局唯一标识生成。

历史上多处模型使用 `str(uuid.uuid4())[:8]`（32-bit 熵），在生产并发下存在
真实碰撞风险。这里提供唯一入口，统一返回带前缀的完整 UUID4（36 字符，
122-bit 熵），既保留既有可读前缀语义，又消除碰撞空间。
"""

from __future__ import annotations

import uuid


def new_id(prefix: str = "") -> str:
    """Return a globally unique identifier, optionally prefixed.

    `new_id("EVID-")` -> "EVID-<full-uuid4>"。调用方负责前缀约定，
    本函数不做格式校验，保证全部调用点返回同一格式。
    """
    return f"{prefix}{uuid.uuid4()}"
