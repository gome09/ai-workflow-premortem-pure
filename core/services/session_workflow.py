# core/services/session_workflow.py
"""Session lifecycle, workflow turns, stage operations and reports."""

from __future__ import annotations

import hashlib

from core.audit_service import append_audit_event
from core.evidence_service import evidence_sources_from_user_materials
from core.execution_service import (
    sync_execution_after_stage_revision,
)
from core.models import ProjectContext, SessionState
from core.report_service import build_markdown_report, build_report_dict, create_report_artifact
from core.scenario_context import attach_scenario_to_context
from core.services.access import (
    DATA_CLASSIFICATION_ORDER,
    DataClassification,
    DataClassificationDowngradeError,
    SessionAccess,
    logger,
)
from core.stage_advancement_coordinator import (
    advance_stage_if_ready as advance_stage_if_ready_operation,
)
from core.stage_advancement_coordinator import (
    build_stage_advancement_decision,
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
from core.workflow_state_service import assert_advanceable, state_value
from core.workflow_state_service import recover_workflow as recover_workflow_operation
from tools.safety_classifier import add_findings_dedup, scan_user_materials


class SessionWorkflowService(SessionAccess):
    def create_session(self, tenant_id: str = "", scenario_id: str | None = None) -> ProjectContext:
        """创建新会话"""
        ctx = ProjectContext(tenant_id=tenant_id)
        # 无 scenario_id 永远创建空白会话。内置场景只能由调用方显式选择，
        # 避免部署环境中的默认值让「新建会话」悄悄携带场景内容。
        ctx = attach_scenario_to_context(ctx, scenario_id)
        # T1.1: 数据分类分级——场景会话 public_demo，用户会话 business_internal
        ctx.data_classification = "public_demo" if ctx.selected_scenario_id else "business_internal"
        self._store().save(ctx)
        self._cache_set(ctx)
        logger.info(f"Session created: {ctx.session_id}")
        return ctx

    def get_session_overview(self, session_id: str, tenant_id: str = "") -> dict | None:
        """轻量概览：只返回前端首屏需要的字段，避免整份上下文响应。"""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            return None
        return {
            "session_id": ctx.session_id,
            "session_name": ctx.session_name,
            "current_state": ctx.current_state.value,
            "selected_scenario_id": ctx.selected_scenario_id,
            "data_classification": ctx.data_classification,
            "created_at": ctx.created_at,
            "updated_at": ctx.updated_at,
            "conversation_history": {
                stage: [message.model_dump(mode="json") for message in messages]
                for stage, messages in ctx.conversation_history.items()
            },
            "flagged_items": [item.model_dump(mode="json") for item in ctx.flagged_items],
            "pending_actions": [action.model_dump(mode="json") for action in ctx.pending_actions],
        }

    def rename_session(self, session_id: str, name: str, tenant_id: str = "") -> dict:
        """重命名会话并记录审计事件。"""
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 80:
            raise ValueError("Session name must contain 1 to 80 characters")

        ctx = self.get_session(session_id, tenant_id=tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        previous_name = ctx.session_name
        if previous_name != normalized_name:
            append_audit_event(
                ctx,
                actor="user",
                event_type="session_renamed",
                target_type="session",
                target_id=session_id,
                before={"session_name": previous_name},
                after={"session_name": normalized_name},
            )
            ctx.session_name = normalized_name
            self._store().save(ctx)
            self._cache_set(ctx)

        return {"session_id": session_id, "session_name": normalized_name}

    def update_data_classification(
        self,
        session_id: str,
        *,
        data_classification: DataClassification,
        note: str = "",
        actor_role: str = "",
        tenant_id: str = "",
    ) -> dict:
        """覆写会话数据分级，并写 data_classification_changed 审计事件。

        规则：升级或同级修改允许 editor+；降级必须 admin。
        角色准入由 API 层保证，本方法只接收 actor_role 用于降级判定与审计。
        """
        ctx = self.get_session(session_id, tenant_id=tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        before = ctx.data_classification
        is_downgrade = (
            DATA_CLASSIFICATION_ORDER[data_classification] < DATA_CLASSIFICATION_ORDER[before]
        )
        if is_downgrade and actor_role != "admin":
            raise DataClassificationDowngradeError(
                "Downgrading data_classification requires admin role"
            )

        append_audit_event(
            ctx,
            actor="user",
            event_type="data_classification_changed",
            target_type="session",
            target_id=session_id,
            before={"data_classification": before},
            after={"data_classification": data_classification},
            metadata={
                "note": note,
                "is_downgrade": is_downgrade,
                "actor_role": actor_role,
            },
        )
        ctx.data_classification = data_classification
        self._store().save(ctx)
        self._cache_set(ctx)
        return {
            "ok": True,
            "session_id": session_id,
            "before": before,
            "after": data_classification,
            "is_downgrade": is_downgrade,
        }

    def delete_session(
        self, session_id: str, *, purged_by: str = "admin", tenant_id: str = ""
    ) -> dict:
        """Admin 删除会话：归档审计事件 → 写 session_purged → 删除会话 → 清缓存。

        Returns session summary dict. Raises ValueError if session not found.
        """
        ctx = self.get_session(session_id, tenant_id=tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        # Build summary before deletion
        summary = {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "session_name": ctx.session_name,
            "research_target": ctx.research_target,
            "domain": ctx.domain,
            "current_state": ctx.current_state.value,
            "data_classification": getattr(ctx, "data_classification", "business_internal"),
            "created_at": ctx.created_at.isoformat(),
            "updated_at": ctx.updated_at.isoformat(),
            "purged_by": purged_by,
        }

        # Delete checkpoints before the authoritative session row. If this
        # fails, keep the session so operators never receive a false purge
        # success while sensitive execution snapshots remain behind.
        from graph.checkpoint_manager import delete_session_checkpoints
        from storage.backends.postgres import PostgresSessionStore

        delete_session_checkpoints(ctx, persistent=isinstance(self._store(), PostgresSessionStore))

        # Archive evidence and delete the business session atomically.
        archived_count = self._store().purge_session(
            session_id,
            tenant_id,
            purged_by,
            summary,
        )
        summary["archived_audit_events"] = archived_count

        # Invalidate cache
        self._cache_delete(session_id, tenant_id)

        logger.info(
            f"Session purged: {session_id} by {purged_by} ({archived_count} events archived)"
        )
        return summary

    def list_sessions(self, limit: int = 20, tenant_id: str = "", offset: int = 0) -> list[dict]:
        """列出最近会话，供前端历史列表使用。"""
        rows = self._store().list_sessions(limit=limit, tenant_id=tenant_id, offset=offset)
        items: list[dict] = []
        for row in rows:
            updated_at = row.get("updated_at", "")
            if hasattr(updated_at, "isoformat"):
                updated_at = updated_at.isoformat()

            items.append(
                {
                    "session_id": row.get("session_id", ""),
                    "current_state": row.get("current_state", SessionState.INIT.value),
                    "session_name": row.get("session_name") or "",
                    "scenario_name": row.get("scenario_name") or "",
                    "research_target": row.get("research_target") or "",
                    "domain": row.get("domain") or "",
                    "updated_at": str(updated_at),
                }
            )
        return items

    def recover_workflow(
        self,
        session_id: str,
        *,
        target_state: str,
        note: str = "",
        tenant_id: str = "",
    ) -> dict:
        """显式恢复处于 ERROR / RECOVERY_REQUIRED 的会话。

        目标状态必须属于可恢复状态集合；恢复动作写审计事件后再落库。
        """
        ctx = self.get_session(session_id, tenant_id=tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        before = state_value(ctx.current_state)
        recover_workflow_operation(ctx, target_state, actor="user", note=note)
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
            event_type="workflow_recovered",
            stage=self._current_stage(ctx),
            payload={"before_state": before, "after_state": state_value(ctx.current_state)},
        )
        return {
            "ok": True,
            "session_id": session_id,
            "before": before,
            "after": state_value(ctx.current_state),
            "last_error": ctx.last_error,
        }

    def send_message(
        self,
        session_id: str,
        user_input: str,
        user_materials: list[str] | None = None,
        tenant_id: str = "",
    ) -> tuple[str, ProjectContext]:
        """
        发送消息，驱动状态机前进一步。
        返回：(AI 最新回复, 更新后的 ctx)
        """
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        # 阻断态与未知状态必须在进入执行引擎前失败关闭。
        assert_advanceable(ctx)

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

        # 驱动执行引擎单步推进。默认 single_step；langgraph_interrupt 为受控 opt-in。
        updated_ctx: ProjectContext = self._run_turn(ctx)

        # 持久化
        self._store().save(updated_ctx)
        self._cache_set(updated_ctx)

        # 记录事件：只落状态与输入指纹，避免用户原文进入事件表。
        self._log_event(
            updated_ctx,
            event_type="message",
            stage=self._current_stage(updated_ctx),
            payload={
                "state": updated_ctx.current_state.value,
                "input_length": len(user_input),
                "input_sha256": hashlib.sha256(user_input.encode("utf-8")).hexdigest(),
                "classification": updated_ctx.data_classification,
            },
        )

        # 提取最新的 AI 回复
        ai_reply = self._extract_latest_reply(updated_ctx)
        return ai_reply, updated_ctx

    def add_materials(self, session_id: str, materials: list[str], tenant_id: str = "") -> dict:
        """追加人工补充资料，并返回刷新后的阶段推进 envelope。"""
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
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

    def create_report_artifact(self, session_id: str, tenant_id: str = "") -> dict:
        """生成版本化报告快照。"""
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        return self._with_stage_advancement(
            ctx,
            operation="report_artifact_created",
            result=artifact,
            source="report_artifact_created",
            stage=self._current_stage(ctx) or 4,
            reason="report_artifact_created",
            metadata={"report_id": artifact.report_id},
        )

    def list_report_artifacts(self, session_id: str, tenant_id: str = "") -> list[dict]:
        exists = self._session_exists(session_id, tenant_id)
        if exists:
            try:
                return self._store().list_report_artifacts(session_id)
            except Exception:
                logger.exception("Failed to list report_artifacts table; falling back to context.")
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [artifact.model_dump(mode="json") for artifact in ctx.report_artifacts]

    def get_report_artifact(self, session_id: str, report_id: str, tenant_id: str = "") -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        try:
            artifact = self._store().get_report_artifact(session_id, report_id)
            if artifact:
                return artifact
        except Exception:
            logger.exception("Failed to read report_artifacts table; falling back to context.")
        for artifact in ctx.report_artifacts:
            if artifact.report_id == report_id:
                return artifact.model_dump(mode="json")
        raise ValueError(f"Report artifact not found: {report_id}")

    def prepare_stage_rerun(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "",
        note: str = "",
        tenant_id: str = "",
    ) -> dict:
        """Prepare a stage for rerun; does not execute pytest/API/frontend/Docker/LLM."""
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
        tenant_id: str = "",
    ) -> dict:
        """Prepare a stage revision; actual regeneration still goes through chat."""
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
        tenant_id: str = "",
    ) -> dict:
        """Rollback stage state; does not execute runtime validation."""
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
        tenant_id: str = "",
    ) -> dict:
        """Explicitly regenerate missing PendingHumanAction records for stage blockers."""
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
            session_id=session_id,
            event_type="stage_review_actions_synced",
            stage=stage_id,
            payload=envelope,
        )
        return envelope

    def get_stage_advancement_decision(
        self, session_id: str, stage_id: int, tenant_id: str = ""
    ) -> dict:
        """Return the unified read-only stage advancement decision."""
        ctx = self.get_session(session_id, tenant_id)
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
        tenant_id: str = "",
    ) -> dict:
        """Advance only when the unified StageAdvancementDecision allows it.

        The public API no longer accepts a caller-controlled source.  The
        service keeps this parameter for internal compatibility but always uses
        the server-owned api_advance source for audit integrity.
        """
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        decision = advance_stage_if_ready_operation(
            ctx,
            stage_id,
            reason=reason or "api_stage_advance",
            source="api_advance",
        )
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
            session_id=session_id,
            event_type="stage_advance_requested",
            stage=stage_id,
            payload=decision.model_dump(mode="json"),
        )
        return decision.model_dump(mode="json")

    def export_report(self, session_id: str, format: str = "json", tenant_id: str = "") -> dict:
        """导出完整分析报告。format 支持 json / markdown。"""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        if format == "markdown":
            return {"format": "markdown", "content": build_markdown_report(ctx)}
        if format != "json":
            raise ValueError("Unsupported export format. Use json or markdown.")
        return build_report_dict(ctx)
