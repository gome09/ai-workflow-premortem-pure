# core/session_service.py
"""
会话服务：封装图的调用逻辑，对外提供干净的接口。
FastAPI 和 Streamlit 都通过此层交互，不直接操作图。
"""

from __future__ import annotations

import logging

from core.eval_dataset_service import (
    add_cases_to_dataset,
    create_dataset,
    create_dataset_from_stage3,
    get_dataset,
    list_datasets,
    remove_cases_from_dataset,
    set_dataset_baseline,
)
from core.eval_experiment_service import (
    compare_experiment_with_baseline,
    create_experiment,
    get_experiment,
    get_experiment_metrics,
    list_experiments,
    run_experiment,
)
from core.eval_judgment_service import (
    calibrate_eval_run as calibrate_eval_run_operation,
)
from core.eval_judgment_service import (
    list_eval_judgments as list_eval_judgments_operation,
)
from core.eval_judgment_service import (
    list_human_calibrations as list_human_calibrations_operation,
)
from core.eval_runner import run_eval_cases as execute_eval_cases
from core.eval_service import score_eval_case
from core.evidence_service import evidence_sources_from_user_materials, verify_evidence_source
from core.execution_service import (
    execute_one_turn,
    sync_execution_after_stage_revision,
)
from core.models import AuditEvent, FlagStatus, LLMTrace, MessageRole, ProjectContext, SessionState
from core.oversight_service import (
    create_actions_from_eval_failures,
    resolve_actions_for_evidence,
    resolve_actions_for_flag,
)
from core.oversight_service import (
    resolve_action as resolve_human_action,
)
from core.oversight_service import (
    resolve_action_with_result as resolve_human_action_with_result,
)
from core.redteam_service import (
    approve_redteam_case as approve_redteam_case_operation,
)
from core.redteam_service import (
    build_redteam_coverage_summary,
)
from core.redteam_service import (
    create_redteam_case as create_redteam_case_operation,
)
from core.redteam_service import (
    create_redteam_dataset as create_redteam_dataset_operation,
)
from core.redteam_service import (
    generate_redteam_cases as generate_redteam_cases_operation,
)
from core.redteam_service import (
    list_redteam_cases as list_redteam_cases_operation,
)
from core.redteam_service import (
    redteam_case_to_eval_case as redteam_case_to_eval_case_operation,
)
from core.redteam_service import (
    reject_redteam_case as reject_redteam_case_operation,
)
from core.report_service import build_markdown_report, build_report_dict, create_report_artifact
from core.safety_service import resolve_safety_finding
from core.stage_advancement_coordinator import (
    advance_stage_if_ready as advance_stage_if_ready_operation,
)
from core.stage_advancement_coordinator import (
    after_human_resolution,
    append_action_resolution_trace,
    build_stage_advancement_decision,
    build_stage_operation_envelope,
)
from core.stage_operation_service import (
    prepare_stage_rerun as prepare_stage_rerun_operation,
)
from core.stage_operation_service import (
    request_stage_revision as request_stage_revision_operation,
)
from core.stage_operation_service import (
    request_stage_rollback as request_stage_rollback_operation,
)
from core.stage_operation_service import (
    stage_operation_payload,
)
from core.stage_operation_service import (
    sync_stage_review_actions as sync_stage_review_actions_operation,
)
from core.stage_resolution_service import get_next_required_operation
from core.trace_backfill_service import (
    convert_trace_to_eval_case,
    create_dataset_from_failed_traces,
)
from storage.cache import context_cache
from storage.session_store import session_store
from tools.safety_classifier import add_findings_dedup, scan_user_materials

logger = logging.getLogger(__name__)


class SessionService:
    def create_session(self) -> ProjectContext:
        """创建新会话"""
        ctx = ProjectContext()
        session_store.save(ctx)
        context_cache.set(ctx)
        logger.info(f"Session created: {ctx.session_id}")
        return ctx

    def get_session(self, session_id: str) -> ProjectContext | None:
        """获取会话（优先从 Redis，回退到 PG）"""
        ctx = context_cache.get(session_id)
        if ctx:
            context_cache.refresh_ttl(session_id)
            return ctx

        ctx = session_store.load(session_id)
        if ctx:
            context_cache.set(ctx)
        return ctx

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """列出最近会话，供前端历史列表使用。"""
        rows = session_store.list_sessions(limit=limit)
        items: list[dict] = []
        for row in rows:
            updated_at = row.get("updated_at", "")
            if hasattr(updated_at, "isoformat"):
                updated_at = updated_at.isoformat()

            items.append(
                {
                    "session_id": row.get("session_id", ""),
                    "current_state": row.get("current_state", SessionState.INIT.value),
                    "research_target": row.get("research_target") or "",
                    "domain": row.get("domain") or "",
                    "updated_at": str(updated_at),
                }
            )
        return items

    def _with_stage_advancement(
        self,
        ctx: ProjectContext,
        *,
        operation: str,
        result,
        source: str,
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

    def send_message(
        self,
        session_id: str,
        user_input: str,
        user_materials: list[str] | None = None,
    ) -> tuple[str, ProjectContext]:
        """
        发送消息，驱动状态机前进一步。
        返回：(AI 最新回复, 更新后的 ctx)
        """
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        # 如果用户附带了补充资料，先合并并立即进行轻量安全扫描。
        if user_materials:
            new_material_start = len(ctx.user_materials)
            ctx.user_materials.extend(user_materials)
            evidence_sources_from_user_materials(
                ctx,
                user_materials,
                start_index=new_material_start,
            )
            add_findings_dedup(
                ctx,
                scan_user_materials(
                    ctx,
                    user_materials,
                    stage_id=self._current_stage(ctx),
                    start_index=new_material_start,
                ),
            )

        # 将用户输入注入 state，供单步 runner 调用当前状态节点。
        ctx.pending_input = user_input

        # 驱动执行引擎单步推进。默认 single_step；langgraph_interrupt 为实验性 adapter。
        updated_ctx: ProjectContext = execute_one_turn(ctx)

        # 持久化
        session_store.save(updated_ctx)
        context_cache.set(updated_ctx)

        # 记录事件
        session_store.log_event(
            session_id=session_id,
            event_type="message",
            stage=self._current_stage(updated_ctx),
            payload={"user_input": user_input, "state": updated_ctx.current_state},
        )

        # 提取最新的 AI 回复
        ai_reply = self._extract_latest_reply(updated_ctx)
        return ai_reply, updated_ctx

    def add_materials(self, session_id: str, materials: list[str]) -> dict:
        """追加人工补充资料，并返回刷新后的阶段推进 envelope。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        new_material_start = len(ctx.user_materials)
        ctx.user_materials.extend(materials)
        evidence_sources_from_user_materials(
            ctx,
            materials,
            start_index=new_material_start,
        )
        add_findings_dedup(
            ctx,
            scan_user_materials(
                ctx,
                materials,
                stage_id=self._current_stage(ctx),
                start_index=new_material_start,
            ),
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="materials_added",
            result={
                "ok": True,
                "materials_added_count": len(materials),
                "user_materials_count": len(ctx.user_materials),
                "evidence_sources_count": len(ctx.evidence_sources),
                "safety_findings_count": len(ctx.safety_findings),
            },
            source="materials_added",
            stage=self._current_stage(ctx) or 1,
            reason="materials_added",
            metadata={"materials_added_count": len(materials)},
        )

    def resolve_flag(
        self,
        session_id: str,
        flag_id: str,
        action: str,  # 'verified' | 'dismissed'
        note: str = "",
    ) -> dict:
        """处理【需核验】项，并同步处理由该 flag 派生的人工动作。"""
        from datetime import datetime

        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        found = False
        for flag in ctx.flagged_items:
            if flag.item_id == flag_id:
                flag.status = FlagStatus(action)
                flag.verified_at = datetime.utcnow()
                flag.note = note
                found = True
                break

        if not found:
            raise ValueError(f"Flag not found: {flag_id}")

        resolved_action_ids = resolve_actions_for_flag(
            ctx,
            flag_id=flag_id,
            decision=action,
            note=note,
        )
        ctx, _decision = after_human_resolution(
            ctx,
            action_ids=resolved_action_ids,
            reason=f"Flag {flag_id} resolved as {action}.",
            source="flag_resolution",
        )

        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="flag_resolved",
            result={
                "ok": True,
                "flag_id": flag_id,
                "action": action,
                "note": note,
                "resolved_action_ids": resolved_action_ids,
                "resolved_actions_count": len(resolved_action_ids),
            },
            source="flag_resolution",
            stage=self._current_stage(ctx) or 1,
            reason=f"Flag {flag_id} resolved as {action}.",
            metadata={
                "flag_id": flag_id,
                "action": action,
                "resolved_action_ids": resolved_action_ids,
            },
        )

    def list_actions(self, session_id: str, status: str | None = None) -> list[dict]:
        """列出人工监督动作。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        actions = ctx.pending_actions
        if status:
            actions = [action for action in actions if action.status == status]
        return [action.model_dump(mode="json") for action in actions]

    def get_action(self, session_id: str, action_id: str) -> dict:
        """获取单个人工监督动作。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        for action in ctx.pending_actions:
            if action.action_id == action_id:
                return action.model_dump(mode="json")
        raise ValueError(f"Action not found: {action_id}")

    def list_action_resolution_logs(self, session_id: str, action_id: str) -> list[dict]:
        """List append-only resolution attempts for one human action."""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [
            log.model_dump(mode="json")
            for log in getattr(ctx, "action_resolution_logs", []) or []
            if log.action_id == action_id
        ]

    def resolve_action_with_result(
        self,
        session_id: str,
        action_id: str,
        decision: str,
        note: str = "",
        payload_after: dict | None = None,
        idempotency_key: str | None = None,
        expected_before_hash: str | None = None,
    ) -> dict:
        """Resolve a formal human action and return the v0.7 result contract."""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        result = resolve_human_action_with_result(
            ctx,
            action_id=action_id,
            decision=decision,
            note=note,
            payload_after=payload_after,
            idempotency_key=idempotency_key,
            expected_before_hash=expected_before_hash,
        )

        action_stage = None
        for action_item in ctx.pending_actions:
            if action_item.action_id == action_id:
                action_stage = action_item.stage_id
                break

        append_action_resolution_trace(
            ctx,
            action_ids=[action_id],
            result_status=result.result_status,
            source="resolve_action_with_result",
            stage=action_stage,
            metadata={"decision": decision, "log_id": result.log_id, "note": note},
        )
        safe_stage = action_stage or self._current_stage(ctx) or 1
        if result.result_status == "resolved":
            ctx, stage_decision = after_human_resolution(
                ctx,
                action_ids=[action_id],
                reason=note or f"Action {action_id} resolved as {decision}.",
                source="action_resolution",
                stage=safe_stage,
            )
            session_store.log_event(
                session_id=session_id,
                event_type="human_action_resolved",
                stage=self._current_stage(ctx),
                payload={
                    "action_id": action_id,
                    "decision": decision,
                    "note": note,
                    "result_status": result.result_status,
                    "log_id": result.log_id,
                    "stage_advancement_decision": stage_decision.model_dump(mode="json"),
                },
            )
        else:
            stage_decision = build_stage_advancement_decision(
                ctx,
                safe_stage,
                decision_source="action_resolution",
                reason=note or f"Action {action_id} resolution result: {result.result_status}.",
                append_trace=True,
                trace_type="gate",
                node_name="post_action_resolution_gate",
                metadata={
                    "action_id": action_id,
                    "result_status": result.result_status,
                    "log_id": result.log_id,
                },
            )

        session_store.save(ctx)
        context_cache.set(ctx)

        payload = result.model_dump(mode="json")
        payload["session_id"] = ctx.session_id
        payload["current_state"] = ctx.current_state.value
        payload["stage_id"] = safe_stage
        payload["stage_advancement_decision"] = stage_decision.model_dump(mode="json")
        payload["next_required_operation"] = get_next_required_operation(ctx, safe_stage)
        payload["runtime_validation"] = "deferred_by_instruction"
        return payload

    def resolve_action(
        self,
        session_id: str,
        action_id: str,
        decision: str,
        note: str = "",
        payload_after: dict | None = None,
        idempotency_key: str | None = None,
        expected_before_hash: str | None = None,
    ) -> ProjectContext:
        """处理正式人工监督动作。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        try:
            resolve_human_action(
                ctx,
                action_id=action_id,
                decision=decision,
                note=note,
                payload_after=payload_after,
                idempotency_key=idempotency_key,
                expected_before_hash=expected_before_hash,
            )
        except Exception:
            # Persist v0.7 resolution_attempts / failure logs without advancing execution.
            session_store.save(ctx)
            context_cache.set(ctx)
            raise
        ctx, stage_decision = after_human_resolution(
            ctx,
            action_ids=[action_id],
            reason=note or f"Action {action_id} resolved as {decision}.",
            source="action_resolution",
        )

        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="human_action_resolved",
            stage=self._current_stage(ctx),
            payload={
                "action_id": action_id,
                "decision": decision,
                "note": note,
                "stage_advancement_decision": stage_decision.model_dump(mode="json"),
            },
        )
        return ctx

    def list_traces(
        self,
        session_id: str,
        stage: int | None = None,
        trace_type: str | None = None,
        parser_status: str | None = None,
    ) -> list[dict]:
        """List traces captured for this session, with lightweight filters."""
        ctx = self.get_session(session_id)
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

    def get_trace(self, session_id: str, trace_id: str) -> dict:
        """Get one LLM trace from the current context snapshot."""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        for trace in getattr(ctx, "llm_traces", []) or []:
            if trace.trace_id == trace_id:
                return trace.model_dump(mode="json")
        raise ValueError(f"Trace not found: {trace_id}")

    def list_audit_events(self, session_id: str) -> list[dict]:
        """列出审计事件。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [event.model_dump(mode="json") for event in ctx.audit_events]

    def list_interrupt_records(self, session_id: str) -> list[dict]:
        """列出当前会话的 interrupt/action 映射记录。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        records = [
            record.model_dump(mode="json") for record in getattr(ctx, "interrupt_records", []) or []
        ]
        if records:
            return records
        try:
            return session_store.list_interrupt_records(session_id)
        except Exception:
            return records

    def get_interrupt_record(self, session_id: str, interrupt_id: str) -> dict:
        """读取单个 interrupt/action 映射记录。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        for record in getattr(ctx, "interrupt_records", []) or []:
            if record.interrupt_id == interrupt_id:
                return record.model_dump(mode="json")
        try:
            item = session_store.get_interrupt_record(session_id, interrupt_id)
        except Exception:
            item = None
        if item:
            return item
        raise ValueError(f"Interrupt record not found: {interrupt_id}")

    def list_evidence(self, session_id: str) -> list[dict]:
        """列出当前会话证据来源。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [ev.model_dump(mode="json") for ev in ctx.evidence_sources]

    def get_evidence(self, session_id: str, evidence_id: str) -> dict:
        """读取单条证据来源。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        for ev in ctx.evidence_sources:
            if ev.evidence_id == evidence_id:
                return ev.model_dump(mode="json")
        raise ValueError(f"Evidence not found: {evidence_id}")

    def verify_evidence(self, session_id: str, evidence_id: str, note: str = "") -> dict:
        """人工核验证据来源，并自动关闭直接相关的低可信证据动作。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        verify_evidence_source(ctx, evidence_id=evidence_id, note=note)
        resolved_action_ids = resolve_actions_for_evidence(
            ctx,
            evidence_id=evidence_id,
            decision="verify_evidence",
            note=note,
        )
        ctx, _decision = after_human_resolution(
            ctx,
            action_ids=resolved_action_ids,
            reason=f"Evidence {evidence_id} verified.",
            source="evidence_resolution",
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="evidence_verified",
            result={
                "ok": True,
                "evidence_id": evidence_id,
                "note": note,
                "resolved_action_ids": resolved_action_ids,
                "resolved_actions_count": len(resolved_action_ids),
            },
            source="evidence_resolution",
            stage=self._current_stage(ctx) or 1,
            reason=f"Evidence {evidence_id} verified.",
            metadata={"evidence_id": evidence_id, "resolved_action_ids": resolved_action_ids},
        )

    def list_safety_findings(self, session_id: str, status: str | None = None) -> list[dict]:
        """列出安全扫描发现。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        findings = ctx.safety_findings
        if status:
            findings = [finding for finding in findings if finding.status == status]
        return [finding.model_dump(mode="json") for finding in findings]

    def resolve_safety_finding(
        self,
        session_id: str,
        finding_id: str,
        status: str,
        note: str = "",
    ) -> dict:
        """处理安全扫描发现。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        before_pending = {
            action.action_id
            for action in ctx.pending_actions
            if action.source_type == "safety_finding"
            and action.source_id == finding_id
            and action.status == "pending"
        }
        resolve_safety_finding(
            ctx,
            finding_id=finding_id,
            status=status,  # type: ignore[arg-type]
            note=note,
        )
        resolved_action_ids = [
            action.action_id
            for action in ctx.pending_actions
            if action.action_id in before_pending and action.status == "resolved"
        ]
        ctx, _decision = after_human_resolution(
            ctx,
            action_ids=resolved_action_ids,
            reason=f"Safety finding {finding_id} resolved as {status}.",
            source="safety_resolution",
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="safety_finding_resolved",
            result={
                "ok": True,
                "finding_id": finding_id,
                "status": status,
                "note": note,
                "resolved_action_ids": resolved_action_ids,
                "resolved_actions_count": len(resolved_action_ids),
            },
            source="safety_resolution",
            stage=self._current_stage(ctx) or 1,
            reason=f"Safety finding {finding_id} resolved as {status}.",
            metadata={
                "finding_id": finding_id,
                "status": status,
                "resolved_action_ids": resolved_action_ids,
            },
        )

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

    def create_report_artifact(self, session_id: str) -> dict:
        """生成版本化报告快照。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        # Build a lightweight context for report generation to avoid OOM
        # with large sessions (936+ traces, 100MB+ audit events).
        report_ctx = self._build_lightweight_context(ctx)
        artifact = create_report_artifact(report_ctx)
        # Transfer artifact and audit events from lightweight copy to original
        ctx.report_artifacts.append(artifact)
        # Transfer any new audit events added by create_report_artifact
        for event in report_ctx.audit_events:
            if not any(e.event_id == event.event_id for e in ctx.audit_events):
                ctx.audit_events.append(event)
        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="report_artifact_created",
            result=artifact,
            source="report_artifact_created",
            stage=self._current_stage(ctx) or 4,
            reason="report_artifact_created",
            metadata={"report_id": artifact.report_id},
        )

    def list_report_artifacts(self, session_id: str) -> list[dict]:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        try:
            artifacts = session_store.list_report_artifacts(session_id)
            if artifacts:
                return artifacts
        except Exception:
            logger.exception("Failed to list report_artifacts table; falling back to context.")
        return [artifact.model_dump(mode="json") for artifact in ctx.report_artifacts]

    def get_report_artifact(self, session_id: str, report_id: str) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        try:
            artifact = session_store.get_report_artifact(session_id, report_id)
            if artifact:
                return artifact
        except Exception:
            logger.exception("Failed to read report_artifacts table; falling back to context.")
        for artifact in ctx.report_artifacts:
            if artifact.report_id == report_id:
                return artifact.model_dump(mode="json")
        raise ValueError(f"Report artifact not found: {report_id}")

    def list_eval_cases(self, session_id: str) -> list[dict]:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [case.model_dump(mode="json") for case in ctx.eval_cases]

    def score_eval_case(
        self,
        session_id: str,
        eval_id: str,
        human_score: int | None = None,
        human_comment: str = "",
        passed: bool | None = None,
        actual_output: str | None = None,
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        score_eval_case(
            ctx,
            eval_id=eval_id,
            human_score=human_score,
            human_comment=human_comment,
            passed=passed,
            actual_output=actual_output,
        )
        create_actions_from_eval_failures(ctx, 3)
        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="eval_case_scored",
            result={
                "ok": True,
                "eval_id": eval_id,
                "human_score": human_score,
                "human_comment": human_comment,
                "passed": passed,
                "actual_output": actual_output,
                "pending_actions_count": len(ctx.get_pending_actions()),
            },
            source="eval_case_scored",
            stage=3,
            reason="eval_case_scored",
            metadata={"eval_id": eval_id, "passed": passed},
        )

    def list_eval_runs(self, session_id: str, eval_id: str | None = None) -> list[dict]:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        runs = ctx.eval_runs
        if eval_id:
            runs = [run for run in runs if run.eval_id == eval_id]
        return [run.model_dump(mode="json") for run in runs]

    def run_eval_cases(
        self,
        session_id: str,
        eval_ids: list[str] | None = None,
        run_mode: str = "manual",
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        runs = execute_eval_cases(ctx, eval_ids=eval_ids, run_mode=run_mode)
        run_payloads = [run.model_dump(mode="json") for run in runs]
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="eval_cases_run",
            stage=3,
            payload={
                "eval_ids": eval_ids or "all",
                "run_mode": run_mode,
                "created_runs": len(runs),
            },
        )
        return self._with_stage_advancement(
            ctx,
            operation="eval_cases_run",
            result={
                "session_id": ctx.session_id,
                "created_runs": run_payloads,
                "created_runs_count": len(run_payloads),
                "eval_runs_count": len(ctx.eval_runs),
                "pending_actions_count": len(ctx.get_pending_actions()),
                "run_mode": run_mode,
                "eval_ids": eval_ids or "all",
            },
            source="eval_cases_run",
            stage=3,
            reason="eval_cases_run",
            metadata={
                "eval_ids": eval_ids or "all",
                "run_mode": run_mode,
                "created_runs_count": len(run_payloads),
            },
        )

    # ── v0.8-alpha.1 Eval Dataset / Experiment foundation ───────────────────

    def list_eval_datasets(self, session_id: str) -> list[dict]:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [dataset.model_dump(mode="json") for dataset in list_datasets(ctx)]

    def get_eval_dataset(self, session_id: str, dataset_id: str) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return get_dataset(ctx, dataset_id).model_dump(mode="json")

    def create_eval_dataset(
        self,
        session_id: str,
        *,
        name: str,
        description: str = "",
        case_ids: list[str] | None = None,
        scenario_type: str = "mixed",
        source: str = "manual",
        version: str = "0.1",
        tags: list[str] | None = None,
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = create_dataset(
            ctx,
            name=name,
            description=description,
            case_ids=case_ids or [],
            scenario_type=scenario_type,
            source=source,
            version=version,
            tags=tags or [],
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="eval_dataset_created",
            stage=3,
            payload=dataset.model_dump(mode="json"),
        )
        return self._with_stage_advancement(
            ctx,
            operation="eval_dataset_created",
            result=dataset,
            source="eval_dataset_created",
            stage=3,
            reason="eval_dataset_created",
            metadata={"dataset_id": dataset.dataset_id, "source": source},
        )

    def create_eval_dataset_from_stage3(
        self,
        session_id: str,
        *,
        name: str,
        description: str = "",
        version: str = "0.1",
        owner: str = "system",
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = create_dataset_from_stage3(
            ctx,
            name=name,
            description=description,
            version=version,
            owner=owner,
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="eval_dataset_created_from_stage3",
            stage=3,
            payload=dataset.model_dump(mode="json"),
        )
        return self._with_stage_advancement(
            ctx,
            operation="eval_dataset_created_from_stage3",
            result=dataset,
            source="eval_dataset_created",
            stage=3,
            reason="eval_dataset_created_from_stage3",
            metadata={"dataset_id": dataset.dataset_id},
        )

    def add_eval_cases_to_dataset(
        self, session_id: str, *, dataset_id: str, eval_ids: list[str]
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = add_cases_to_dataset(ctx, dataset_id=dataset_id, eval_ids=eval_ids)
        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="eval_dataset_cases_added",
            result=dataset,
            source="eval_dataset_updated",
            stage=3,
            reason="eval_dataset_cases_added",
            metadata={"dataset_id": dataset.dataset_id, "eval_ids": eval_ids},
        )

    def remove_eval_cases_from_dataset(
        self, session_id: str, *, dataset_id: str, eval_ids: list[str]
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = remove_cases_from_dataset(ctx, dataset_id=dataset_id, eval_ids=eval_ids)
        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="eval_dataset_cases_removed",
            result=dataset,
            source="eval_dataset_updated",
            stage=3,
            reason="eval_dataset_cases_removed",
            metadata={"dataset_id": dataset.dataset_id, "eval_ids": eval_ids},
        )

    def set_eval_dataset_baseline(
        self,
        session_id: str,
        *,
        dataset_id: str,
        baseline_experiment_id: str | None,
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = set_dataset_baseline(
            ctx,
            dataset_id=dataset_id,
            baseline_experiment_id=baseline_experiment_id,
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="eval_baseline_set",
            result=dataset,
            source="eval_baseline_set",
            stage=3,
            reason="eval_baseline_set",
            metadata={
                "dataset_id": dataset.dataset_id,
                "baseline_experiment_id": baseline_experiment_id,
            },
        )

    def list_eval_experiments(self, session_id: str) -> list[dict]:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [experiment.model_dump(mode="json") for experiment in list_experiments(ctx)]

    def get_eval_experiment(self, session_id: str, experiment_id: str) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return get_experiment(ctx, experiment_id).model_dump(mode="json")

    def create_eval_experiment(
        self,
        session_id: str,
        *,
        dataset_id: str,
        name: str,
        description: str = "",
        run_mode: str = "manual",
        provider: str | None = None,
        model: str | None = None,
        baseline_experiment_id: str | None = None,
        run_config: dict | None = None,
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        experiment = create_experiment(
            ctx,
            dataset_id=dataset_id,
            name=name,
            description=description,
            run_mode=run_mode,
            provider=provider,
            model=model,
            baseline_experiment_id=baseline_experiment_id,
            run_config=run_config or {},
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="eval_experiment_created",
            stage=3,
            payload=experiment.model_dump(mode="json"),
        )
        return self._with_stage_advancement(
            ctx,
            operation="eval_experiment_created",
            result=experiment,
            source="eval_experiment_created",
            stage=3,
            reason="eval_experiment_created",
            metadata={
                "experiment_id": experiment.experiment_id,
                "dataset_id": experiment.dataset_id,
            },
        )

    def run_eval_experiment(
        self, session_id: str, *, experiment_id: str, dry_run_only: bool = True
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        experiment = run_experiment(ctx, experiment_id=experiment_id, dry_run_only=dry_run_only)
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="eval_experiment_run",
            stage=3,
            payload=experiment.model_dump(mode="json"),
        )
        return self._with_stage_advancement(
            ctx,
            operation="eval_experiment_run",
            result=experiment,
            source="eval_experiment_run",
            stage=3,
            reason="eval_experiment_run",
            metadata={
                "experiment_id": experiment.experiment_id,
                "dataset_id": experiment.dataset_id,
                "dry_run_only": dry_run_only,
            },
        )

    def get_eval_experiment_metrics(self, session_id: str, experiment_id: str) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        metrics = get_experiment_metrics(ctx, experiment_id=experiment_id)
        return metrics.model_dump(mode="json")

    def compare_eval_experiment(
        self,
        session_id: str,
        *,
        experiment_id: str,
        baseline_experiment_id: str | None = None,
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        comparison = compare_experiment_with_baseline(
            ctx,
            experiment_id=experiment_id,
            baseline_experiment_id=baseline_experiment_id,
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="eval_experiment_compared",
            stage=3,
            payload=comparison,
        )
        return self._with_stage_advancement(
            ctx,
            operation="eval_experiment_compared",
            result=comparison,
            source="eval_experiment_compared",
            stage=3,
            reason="eval_experiment_compared",
            metadata={
                "experiment_id": experiment_id,
                "baseline_experiment_id": baseline_experiment_id,
            },
        )

    # ── v0.8-alpha.5 Eval judgment and human calibration ─────────────────────

    def list_eval_judgments(
        self,
        session_id: str,
        *,
        eval_run_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[dict]:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [
            item.model_dump(mode="json")
            for item in list_eval_judgments_operation(
                ctx, eval_run_id=eval_run_id, experiment_id=experiment_id
            )
        ]

    def list_human_calibrations(
        self,
        session_id: str,
        *,
        eval_run_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[dict]:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [
            item.model_dump(mode="json")
            for item in list_human_calibrations_operation(
                ctx, eval_run_id=eval_run_id, experiment_id=experiment_id
            )
        ]

    def calibrate_eval_run(
        self,
        session_id: str,
        *,
        run_id: str,
        human_label: str,
        human_comment: str = "",
        reviewer_id: str = "human_reviewer",
        disagreement_reason: str = "",
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        calibration = calibrate_eval_run_operation(
            ctx,
            eval_run_id=run_id,
            human_label=human_label,  # type: ignore[arg-type]
            human_comment=human_comment,
            reviewer_id=reviewer_id,
            disagreement_reason=disagreement_reason,
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="eval_run_human_calibrated",
            stage=3,
            payload=calibration.model_dump(mode="json"),
        )
        return self._with_stage_advancement(
            ctx,
            operation="eval_run_calibrated",
            result=calibration,
            source="eval_run_calibrated",
            stage=3,
            reason="eval_run_calibrated",
            metadata={"eval_run_id": run_id, "human_label": human_label},
        )

    # ── v0.8-alpha.6 trace backfill ──────────────────────────────────────────

    def trace_to_eval_case(
        self,
        session_id: str,
        *,
        trace_id: str,
        expected_behavior: str | None = None,
        target_node_id: str | None = None,
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        eval_case = convert_trace_to_eval_case(
            ctx,
            trace_id=trace_id,
            expected_behavior=expected_behavior,
            target_node_id=target_node_id,
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="trace_backfilled_to_eval_case",
            stage=eval_case.stage_id,
            payload={"trace_id": trace_id, "eval_id": eval_case.eval_id},
        )
        return self._with_stage_advancement(
            ctx,
            operation="trace_backfilled_to_eval_case",
            result=eval_case,
            source="trace_backfilled_to_eval_case",
            stage=eval_case.stage_id,
            reason="trace_backfilled_to_eval_case",
            metadata={"trace_id": trace_id, "eval_id": eval_case.eval_id},
        )

    def traces_to_eval_dataset(
        self,
        session_id: str,
        *,
        trace_ids: list[str] | None = None,
        name: str = "Trace backfill regression dataset",
        description: str = "EvalCases generated from failed/parser/safety traces for regression gating.",
        version: str = "0.1",
        owner: str = "system",
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = create_dataset_from_failed_traces(
            ctx,
            trace_ids=trace_ids,
            name=name,
            description=description,
            version=version,
            owner=owner,
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="trace_backfill_dataset_created",
            stage=3,
            payload=dataset.model_dump(mode="json"),
        )
        return self._with_stage_advancement(
            ctx,
            operation="trace_backfill_dataset_created",
            result=dataset,
            source="trace_backfill_dataset_created",
            stage=3,
            reason="trace_backfill_dataset_created",
            metadata={"dataset_id": dataset.dataset_id, "trace_ids": trace_ids},
        )

    # ── v0.8-alpha.3 Red Team foundation ────────────────────────────────────

    def list_redteam_cases(self, session_id: str) -> list[dict]:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [case.model_dump(mode="json") for case in list_redteam_cases_operation(ctx)]

    def redteam_coverage_summary(self, session_id: str) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return build_redteam_coverage_summary(ctx, stage=3)

    def generate_redteam_cases(self, session_id: str, *, stage: int = 3) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        cases = generate_redteam_cases_operation(ctx, stage=stage)
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="redteam_cases_generated",
            stage=stage,
            payload={"created_count": len(cases)},
        )
        return self._with_stage_advancement(
            ctx,
            operation="redteam_cases_generated",
            result=cases,
            source="redteam_cases_generated",
            stage=stage,
            reason="redteam_cases_generated",
            metadata={"created_count": len(cases)},
        )

    def create_redteam_case(self, session_id: str, **kwargs) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        case = create_redteam_case_operation(ctx, generated_by="human", **kwargs)
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="redteam_case_created",
            stage=case.target_stage,
            payload=case.model_dump(mode="json"),
        )
        return self._with_stage_advancement(
            ctx,
            operation="redteam_case_created",
            result=case,
            source="redteam_case_created",
            stage=case.target_stage,
            reason="redteam_case_created",
            metadata={"redteam_case_id": case.redteam_case_id},
        )

    def approve_redteam_case(self, session_id: str, case_id: str, *, note: str = "") -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        case = approve_redteam_case_operation(ctx, case_id, note=note)
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="redteam_case_approved",
            stage=case.target_stage,
            payload={"redteam_case_id": case.redteam_case_id, "note": note},
        )
        return self._with_stage_advancement(
            ctx,
            operation="redteam_case_approved",
            result=case,
            source="redteam_case_approved",
            stage=case.target_stage,
            reason="redteam_case_approved",
            metadata={"redteam_case_id": case.redteam_case_id, "note": note},
        )

    def reject_redteam_case(self, session_id: str, case_id: str, *, note: str = "") -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        case = reject_redteam_case_operation(ctx, case_id, note=note)
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="redteam_case_rejected",
            stage=case.target_stage,
            payload={"redteam_case_id": case.redteam_case_id, "note": note},
        )
        return self._with_stage_advancement(
            ctx,
            operation="redteam_case_rejected",
            result=case,
            source="redteam_case_rejected",
            stage=case.target_stage,
            reason="redteam_case_rejected",
            metadata={"redteam_case_id": case.redteam_case_id, "note": note},
        )

    def redteam_case_to_eval_case(self, session_id: str, case_id: str) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        eval_case = redteam_case_to_eval_case_operation(ctx, case_id)
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="redteam_case_synced_to_eval",
            stage=eval_case.stage_id,
            payload={"redteam_case_id": case_id, "eval_id": eval_case.eval_id},
        )
        return self._with_stage_advancement(
            ctx,
            operation="redteam_case_synced",
            result=eval_case,
            source="redteam_case_synced",
            stage=eval_case.stage_id,
            reason="redteam_case_synced",
            metadata={"redteam_case_id": case_id, "eval_id": eval_case.eval_id},
        )

    def create_redteam_dataset(
        self,
        session_id: str,
        *,
        name: str = "Red Team generated dataset",
        description: str = "Approved RedTeamCase records synced into EvalCase for regression gate use.",
        case_ids: list[str] | None = None,
        version: str = "0.1",
        owner: str = "system",
    ) -> dict:
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = create_redteam_dataset_operation(
            ctx,
            name=name,
            description=description,
            case_ids=case_ids,
            version=version,
            owner=owner,
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="redteam_dataset_created",
            stage=3,
            payload=dataset.model_dump(mode="json"),
        )
        return self._with_stage_advancement(
            ctx,
            operation="redteam_dataset_created",
            result=dataset,
            source="redteam_dataset_created",
            stage=3,
            reason="redteam_dataset_created",
            metadata={"dataset_id": dataset.dataset_id},
        )

    def prepare_stage_rerun(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "",
        note: str = "",
    ) -> dict:
        """Prepare a stage for rerun; does not execute pytest/API/frontend/Docker/LLM."""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        result = prepare_stage_rerun_operation(ctx, stage=stage_id, reason=reason, note=note)
        ctx = sync_execution_after_stage_revision(
            ctx,
            stage_id,
            reason=reason or f"Stage {stage_id} rerun prepared.",
            superseded_action_ids=result.superseded_action_ids,
        )
        payload = stage_operation_payload(result)
        envelope = self._with_stage_advancement(
            ctx,
            operation="stage_rerun_prepared",
            result=payload,
            source="stage_rerun",
            stage=stage_id,
            reason=reason or f"Stage {stage_id} rerun prepared.",
            metadata={"mutation_status": payload.get("mutation_status")},
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="stage_rerun_prepared",
            stage=stage_id,
            payload=envelope,
        )
        return envelope

    def request_stage_revision(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "",
        note: str = "",
    ) -> dict:
        """Prepare a stage revision; actual regeneration still goes through chat."""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        result = request_stage_revision_operation(ctx, stage=stage_id, reason=reason, note=note)
        ctx = sync_execution_after_stage_revision(
            ctx,
            stage_id,
            reason=reason or f"Stage {stage_id} revision requested.",
            superseded_action_ids=result.superseded_action_ids,
        )
        payload = stage_operation_payload(result)
        envelope = self._with_stage_advancement(
            ctx,
            operation="stage_revision_prepared",
            result=payload,
            source="stage_revision",
            stage=stage_id,
            reason=reason or f"Stage {stage_id} revision requested.",
            metadata={"mutation_status": payload.get("mutation_status")},
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="stage_revision_prepared",
            stage=stage_id,
            payload=envelope,
        )
        return envelope

    def request_stage_rollback(
        self,
        session_id: str,
        *,
        from_stage: int,
        to_stage: int,
        reason: str = "",
        note: str = "",
        target_running: bool = False,
    ) -> dict:
        """Rollback stage state; does not execute runtime validation."""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        result = request_stage_rollback_operation(
            ctx,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=reason,
            note=note,
            target_running=target_running,
        )
        ctx = sync_execution_after_stage_revision(
            ctx,
            from_stage,
            reason=reason or f"Stage {from_stage} rollback requested.",
            superseded_action_ids=result.superseded_action_ids,
        )
        payload = stage_operation_payload(result)
        envelope = self._with_stage_advancement(
            ctx,
            operation="stage_rollback_prepared",
            result=payload,
            source="stage_rollback",
            stage=from_stage,
            reason=reason or f"Stage {from_stage} rollback requested.",
            metadata={"mutation_status": payload.get("mutation_status"), "to_stage": to_stage},
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="stage_rollback_prepared",
            stage=from_stage,
            payload=envelope,
        )
        return envelope

    def sync_stage_review_actions(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "manual_sync_review_actions",
    ) -> dict:
        """Explicitly regenerate missing PendingHumanAction records for stage blockers."""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        result = sync_stage_review_actions_operation(ctx, stage=stage_id, reason=reason)
        payload = stage_operation_payload(result)
        envelope = self._with_stage_advancement(
            ctx,
            operation="stage_review_actions_synced",
            result=payload,
            source="sync_review_actions",
            stage=stage_id,
            reason=reason,
            metadata={"created_action_ids": payload.get("created_action_ids", [])},
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="stage_review_actions_synced",
            stage=stage_id,
            payload=envelope,
        )
        return envelope

    def get_stage_advancement_decision(self, session_id: str, stage_id: int) -> dict:
        """Return the unified read-only stage advancement decision."""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        decision = build_stage_advancement_decision(
            ctx,
            stage_id,
            decision_source="stage_gate",
            reason="read_stage_advancement_decision",
            append_trace=False,
        )
        return decision.model_dump(mode="json")

    def advance_stage_if_ready(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "",
        source: str = "api_advance",
    ) -> dict:
        """Advance only when the unified StageAdvancementDecision allows it.

        The public API no longer accepts a caller-controlled source.  The
        service keeps this parameter for internal compatibility but always uses
        the server-owned api_advance source for audit integrity.
        """
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        decision = advance_stage_if_ready_operation(
            ctx,
            stage_id,
            reason=reason or "api_stage_advance",
            source="api_advance",
        )
        session_store.save(ctx)
        context_cache.set(ctx)
        session_store.log_event(
            session_id=session_id,
            event_type="stage_advance_requested",
            stage=stage_id,
            payload=decision.model_dump(mode="json"),
        )
        return decision.model_dump(mode="json")

    def export_report(self, session_id: str, format: str = "json") -> dict:
        """导出完整分析报告。format 支持 json / markdown。"""
        ctx = self.get_session(session_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        if format == "markdown":
            return {"format": "markdown", "content": build_markdown_report(ctx)}
        if format != "json":
            raise ValueError("Unsupported export format. Use json or markdown.")
        return build_report_dict(ctx)

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


session_service = SessionService()
