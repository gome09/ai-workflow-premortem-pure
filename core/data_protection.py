# core/data_protection.py
"""统一脱敏策略：event / audit 数据不得无必要携带敏感原文。

设计原则：
- `public_demo` 会话保留可读审计（离线演示卖点）。
- 其余分级（`business_internal` / `sensitive_personal`）对自由文本字段写入
  确定性摘要信封 `{"_redacted": True, "sha256": ..., "length": ...}`，
  保留可复核性与体积信息，但不落原文。
- 判定只依赖输入与 data_classification，同输入必得同输出（deterministic）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# 需要脱敏的自由文本字段名。命中即整值替换为摘要信封。
FREE_TEXT_KEYS: frozenset[str] = frozenset(
    {
        "user_input",
        "note",
        "reviewer_note",
        "description",
        "trigger_reason",
        "summary",
        "claims",
        "content",
        "content_markdown",
        "content_json",
        "raw_summary",
        "user_materials",
        "materials",
        "payload_before",
        "payload_after",
        "title",
    }
)

# 非敏感字符串的最大保留长度；超出截断，避免 audit 表被长文本撑爆。
MAX_PLAIN_STRING = 200

_PUBLIC_CLASSIFICATION = "public_demo"


def _digest(value: Any) -> str:
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def redacted_envelope(value: Any) -> dict[str, Any]:
    """Deterministic digest envelope replacing a sensitive value."""
    raw_len = (
        len(value)
        if isinstance(value, str)
        else len(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False))
    )
    envelope: dict[str, Any] = {
        "_redacted": True,
        "sha256": _digest(value),
        "length": raw_len,
    }
    if isinstance(value, dict):
        envelope["keys"] = sorted(str(key) for key in value.keys())
    return envelope


def redact_payload(value: Any, classification: str) -> Any:
    """Recursively redact a payload for event/audit persistence."""
    if classification == _PUBLIC_CLASSIFICATION:
        return value
    if isinstance(value, dict):
        return {
            key: (
                redacted_envelope(item)
                if key in FREE_TEXT_KEYS
                else redact_payload(item, classification)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_payload(item, classification) for item in value]
    if isinstance(value, str):
        if len(value) <= MAX_PLAIN_STRING:
            return value
        return value[:MAX_PLAIN_STRING] + f"...<truncated:{len(value)} chars>"
    return value


def snapshot(value: Any, classification: str) -> dict[str, Any] | None:
    """Normalize a model/dict into a redacted audit snapshot."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        value = {"value": value}
    redacted = redact_payload(value, classification)
    return redacted if isinstance(redacted, dict) else {"value": redacted}
