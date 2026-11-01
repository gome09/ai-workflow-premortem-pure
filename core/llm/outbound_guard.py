# core/llm/outbound_guard.py
"""Outbound PII guard for external LLM calls.

``sensitive_personal`` 会话的出站消息始终做四类 PII 掩码，不受
``PII_MASK_BEFORE_LLM`` 开关影响；其余数据分级继续沿用该开关。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage

from core.config import settings
from tools.safety_classifier import mask_pii_in_text

SENSITIVE_CLASSIFICATION = "sensitive_personal"


class OutboundPIIBlockedError(RuntimeError):
    """Raised when sensitive content cannot be proven masked before sending."""


def should_mask(classification: str) -> bool:
    """Sensitive personal data must always be masked; others follow the flag."""
    return classification == SENSITIVE_CLASSIFICATION or settings.pii_mask_before_llm


def guard_messages(
    messages: list[BaseMessage],
    *,
    classification: str,
) -> list[BaseMessage]:
    """Return messages safe for an external provider."""
    if not should_mask(classification):
        return list(messages)

    guarded: list[BaseMessage] = []
    for message in messages:
        content = message.content
        if isinstance(content, str):
            guarded.append(message.model_copy(update={"content": mask_pii_in_text(content)}))
            continue
        if classification == SENSITIVE_CLASSIFICATION:
            # 非文本内容无法保证脱敏，对敏感分级 fail-closed。
            raise OutboundPIIBlockedError(
                "Sensitive LLM message content is not plain text; cannot guarantee PII masking"
            )
        guarded.append(message)
    return guarded


def guarded_invoke(llm: Any, messages: list[BaseMessage], *, ctx: Any, stage: int) -> Any:
    """Invoke an LLM after enforcing the outbound PII policy for *ctx*."""
    classification = getattr(ctx, "data_classification", "business_internal")
    return llm.invoke(guard_messages(messages, classification=classification))
