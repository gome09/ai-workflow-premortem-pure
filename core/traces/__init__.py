# core/traces/__init__.py
from core.traces.trace_service import append_llm_trace, create_llm_trace

__all__ = ["append_llm_trace", "create_llm_trace"]
