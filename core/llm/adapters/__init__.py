# core/llm/adapters/__init__.py
from __future__ import annotations

from core.llm.adapters.mock import MockStructuredOutputProvider
from core.llm.adapters.openai_compatible import OpenAICompatibleStructuredOutputProvider

__all__ = ["MockStructuredOutputProvider", "OpenAICompatibleStructuredOutputProvider"]
