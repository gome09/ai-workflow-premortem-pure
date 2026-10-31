# core/services/access.py
"""Storage/cache access shared by domain services.

The module reads the globals from ``core.session_service`` lazily so existing
tests can keep patching ``core.session_service.session_store`` /
``context_cache`` / ``execute_one_turn``.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from typing import Any, Literal

from core.data_protection import redact_payload
from core.models import AuditEvent, LLMTrace, MessageRole, ProjectContext, SessionState
from core.stage_advancement_coordinator import build_stage_operation_envelope
from core.stage_advancement_decision import DecisionSource

logger = logging.getLogger(__name__)

DataClassification = Literal["public_demo", "business_internal", "sensitive_personal"]

DATA_CLASSIFICATION_ORDER: dict[str, int] = {
    "public_demo": 0,
    "business_internal": 1,
    "sensitive_personal": 2,
}


class DataClassificationDowngradeError(PermissionError):
    """调用方不具备 admin 权限却尝试降低数据分级时抛出。"""


def _sha256(value: str | None) -> str:
    """计算自由文本指纹，用于在不落原文的前提下保留可审计关联。"""
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


class SessionAccess:
    """I/O and envelope helpers shared by all domain services."""

    def __init__(
        self,
        session_getter: Callable[[str, str], ProjectContext | None] | None = None,
    ) -> None:
        # The facade injects a dynamic getter so tests that patch
        # ``SessionService.get_session`` keep working for domain calls.
        self._session_getter = session_getter

    @staticmethod
    def _module():
        from core import session_service as module

        return module

    def _store(self):
        return self._module().session_store

    def _cache(self):
        return self._module().context_cache

    def _save(self, ctx: ProjectContext) -> None:
        self._store().save(ctx)

    def _cache_set(self, ctx: ProjectContext) -> None:
        self._cache().set(ctx)

    def _cache_delete(self, session_id: str, tenant_id: str = "") -> None:
        self._cache().delete(session_id, tenant_id)

    def _run_turn(self, ctx: ProjectContext) -> ProjectContext:
        return self._module().execute_one_turn(ctx)

    def get_session(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
        if self._session_getter is not None:
            return self._session_getter(session_id, tenant_id)
        return self._load_session_direct(session_id, tenant_id)

    def _load_session_direct(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
        """获取会话（优先从 Redis，回退到 PG）"""
        ctx = self._cache().get(session_id, tenant_id)
        if ctx:
            self._cache().refresh_ttl(session_id, tenant_id)
            return ctx

        ctx = self._store().load(session_id, tenant_id)
        if ctx:
            self._cache_set(ctx)
        return ctx

    def _projection_rows(
        self,
        table: str,
        session_id: str,
        tenant_id: str = "",
        filters: dict[str, Any] | None = None,
    ) -> list[dict] | None:
        """投影表直读；None 表示不可用或会话不存在，交给调用方回退上下文路径。"""
        reader = getattr(self._store(), "list_projection", None)
        if reader is None:
            return None
        try:
            return reader(table, session_id, tenant_id, filters=filters)
        except Exception:
            logger.exception(
                "Projection read failed for %s (session=%s); falling back to context.",
                table,
                session_id,
            )
            return None

    def _session_exists(self, session_id: str, tenant_id: str = "") -> bool | None:
        """会话存在性探测；None 表示后端不支持，应走旧路径。"""
        checker = getattr(self._store(), "session_exists", None)
        if checker is None:
            return None
        try:
            return bool(checker(session_id, tenant_id))
        except Exception:
            logger.exception("Session existence check failed for %s.", session_id)
            return None

    def _with_stage_advancement(
        self,
        ctx: ProjectContext,
        *,
        operation: str,
        result,
        source: DecisionSource,
        stage: int = 3,
        reason: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """Return the current StageOperationEnvelope while preserving dict payload keys."""
        envelope = build_stage_operation_envelope(
            ctx,
            operation=operation,
            result=result,
            stage=stage,
            source=source,
            reason=reason or operation,
            metadata=metadata or {},
        ).model_dump(mode="json")

        if isinstance(envelope.get("result"), dict):
            return {**envelope["result"], **envelope}
        if isinstance(envelope.get("result"), list):
            envelope["items"] = envelope["result"]
        return envelope

    @staticmethod
    def _build_lightweight_context(ctx: ProjectContext) -> ProjectContext:
        """Create a lightweight copy of context for report generation.

        Truncates LLM trace metadata and audit event snapshots to avoid OOM
        with large sessions (936+ traces, 100MB+ audit events).
        Full data is preserved in the original context and synced tables.
        """
        # Truncate LLM traces — keep summary fields only
        lightweight_traces = []
        for trace in ctx.llm_traces:
            lightweight_traces.append(
                LLMTrace(
                    trace_id=trace.trace_id,
                    session_id=trace.session_id,
                    stage=trace.stage,
                    node_name=trace.node_name,
                    trace_type=trace.trace_type,
                    provider=trace.provider,
                    model=trace.model,
                    prompt_template_id=trace.prompt_template_id,
                    prompt_template_version=trace.prompt_template_version,
                    input_token_count=trace.input_token_count,
                    output_token_count=trace.output_token_count,
                    estimated_cost=trace.estimated_cost,
                    latency_ms=trace.latency_ms,
                    retry_count=trace.retry_count,
                    parser_status=trace.parser_status,
                    safety_status=trace.safety_status,
                    evidence_count=trace.evidence_count,
                    error_type=trace.error_type,
                    error_message=trace.error_message,
                    metadata={},  # Drop large metadata — full data in llm_traces table
                    created_at=trace.created_at,
                )
            )

        # Truncate audit event snapshots
        lightweight_audit = []
        for event in ctx.audit_events:
            lightweight_audit.append(
                AuditEvent(
                    event_id=event.event_id,
                    session_id=event.session_id,
                    actor=event.actor,
                    event_type=event.event_type,
                    target_type=event.target_type,
                    target_id=event.target_id,
                    before_hash=event.before_hash,
                    after_hash=event.after_hash,
                    before_snapshot=None,  # Drop large snapshots
                    after_snapshot=None,  # Drop large snapshots
                    metadata=event.metadata,
                    created_at=event.created_at,
                )
            )

        # Create a copy with truncated fields
        return ctx.model_copy(
            update={
                "llm_traces": lightweight_traces,
                "audit_events": lightweight_audit,
            }
        )

    def _log_event(
        self,
        ctx: ProjectContext,
        *,
        event_type: str,
        payload: dict[str, Any] | None = None,
        stage: int | None = None,
        session_id: str = "",
    ) -> None:
        """统一事件写入入口：先按数据分级脱敏，再落 session_events。"""
        classification = getattr(ctx, "data_classification", "business_internal")
        self._store().log_event(
            session_id=session_id or ctx.session_id,
            event_type=event_type,
            stage=stage,
            payload=redact_payload(payload or {}, classification),
        )

    def _current_stage(self, ctx: ProjectContext) -> int | None:
        stage_map = {
            SessionState.INIT: 0,
            SessionState.S1_RUNNING: 1,
            SessionState.S1_REVIEW: 1,
            SessionState.S2_RUNNING: 2,
            SessionState.S2_REVIEW: 2,
            SessionState.S3_RUNNING: 3,
            SessionState.S3_REVIEW: 3,
            SessionState.S4_RUNNING: 4,
            SessionState.S4_REVIEW: 4,
        }
        return stage_map.get(ctx.current_state)

    def _extract_latest_reply(self, ctx: ProjectContext) -> str:
        """从所有阶段历史中取时间最新的一条 AI 回复。"""
        latest = None
        for history in ctx.conversation_history.values():
            for msg in history:
                if msg.role == MessageRole.ASSISTANT:
                    if latest is None or msg.timestamp > latest.timestamp:
                        latest = msg
        return latest.content if latest else ""
