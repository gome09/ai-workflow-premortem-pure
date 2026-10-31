# core/services/audit_trace.py
"""Audit event, trace and interrupt-record reads."""

from __future__ import annotations

from core.services.access import (
    SessionAccess,
)


class AuditTraceService(SessionAccess):
    def list_traces(
        self,
        session_id: str,
        stage: int | None = None,
        trace_type: str | None = None,
        parser_status: str | None = None,
        tenant_id: str = "",
    ) -> list[dict]:
        """List traces captured for this session, with lightweight filters."""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        traces = list(getattr(ctx, "llm_traces", []) or [])
        if stage is not None:
            traces = [trace for trace in traces if trace.stage == stage]
        if trace_type:
            traces = [trace for trace in traces if trace.trace_type == trace_type]
        if parser_status:
            traces = [trace for trace in traces if trace.parser_status == parser_status]
        return [trace.model_dump(mode="json") for trace in traces]

    def get_trace(self, session_id: str, trace_id: str, tenant_id: str = "") -> dict:
        """Get one LLM trace from the current context snapshot."""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        for trace in getattr(ctx, "llm_traces", []) or []:
            if trace.trace_id == trace_id:
                return trace.model_dump(mode="json")
        raise ValueError(f"Trace not found: {trace_id}")

    def list_audit_events(self, session_id: str, tenant_id: str = "") -> list[dict]:
        """列出审计事件。"""
        rows = self._projection_rows("audit_events", session_id, tenant_id)
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [event.model_dump(mode="json") for event in ctx.audit_events]

    def list_interrupt_records(self, session_id: str, tenant_id: str = "") -> list[dict]:
        """列出当前会话的 interrupt/action 映射记录。"""
        rows = self._projection_rows("interrupt_records", session_id, tenant_id)
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        records = [
            record.model_dump(mode="json") for record in getattr(ctx, "interrupt_records", []) or []
        ]
        if records:
            return records
        try:
            return self._store().list_interrupt_records(session_id)
        except Exception:
            return records

    def get_interrupt_record(self, session_id: str, interrupt_id: str, tenant_id: str = "") -> dict:
        """读取单个 interrupt/action 映射记录。"""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        for record in getattr(ctx, "interrupt_records", []) or []:
            if record.interrupt_id == interrupt_id:
                return record.model_dump(mode="json")
        try:
            item = self._store().get_interrupt_record(session_id, interrupt_id)
        except Exception:
            item = None
        if item:
            return item
        raise ValueError(f"Interrupt record not found: {interrupt_id}")
