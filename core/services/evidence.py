# core/services/evidence.py
"""Evidence and safety-finding operations."""

from __future__ import annotations

from core.evidence_service import verify_evidence_source
from core.execution_service import (
    prepare_execution_after_action_resolutions,
)
from core.oversight_service import (
    resolve_actions_for_evidence,
)
from core.safety_service import resolve_safety_finding
from core.services.access import (
    SessionAccess,
)
from core.stage_advancement_coordinator import (
    after_human_resolution,
)


class EvidenceService(SessionAccess):
    def list_evidence(self, session_id: str, tenant_id: str = "") -> list[dict]:
        """列出当前会话证据来源。"""
        rows = self._projection_rows("evidence_sources", session_id, tenant_id)
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [ev.model_dump(mode="json") for ev in ctx.evidence_sources]

    def get_evidence(self, session_id: str, evidence_id: str, tenant_id: str = "") -> dict:
        """读取单条证据来源。"""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        for ev in ctx.evidence_sources:
            if ev.evidence_id == evidence_id:
                return ev.model_dump(mode="json")
        raise ValueError(f"Evidence not found: {evidence_id}")

    def verify_evidence(
        self, session_id: str, evidence_id: str, note: str = "", tenant_id: str = ""
    ) -> dict:
        """人工核验证据来源，并自动关闭直接相关的低可信证据动作。"""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        verify_evidence_source(ctx, evidence_id=evidence_id, note=note)
        resolved_action_ids = resolve_actions_for_evidence(
            ctx,
            evidence_id=evidence_id,
            decision="verify_evidence",
            note=note,
        )
        prepare_execution_after_action_resolutions(ctx, resolved_action_ids)
        self._store().save(ctx)
        self._cache_set(ctx)
        ctx, _decision = after_human_resolution(
            ctx,
            action_ids=resolved_action_ids,
            reason=f"Evidence {evidence_id} verified.",
            source="evidence_resolution",
        )
        self._store().save(ctx)
        self._cache_set(ctx)
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

    def list_safety_findings(
        self, session_id: str, status: str | None = None, tenant_id: str = ""
    ) -> list[dict]:
        """列出安全扫描发现。"""
        rows = self._projection_rows(
            "safety_findings",
            session_id,
            tenant_id,
            {"status": status} if status else None,
        )
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
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
        tenant_id: str = "",
    ) -> dict:
        """处理安全扫描发现。"""
        ctx = self.get_session(session_id, tenant_id)
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
        prepare_execution_after_action_resolutions(ctx, resolved_action_ids)
        self._store().save(ctx)
        self._cache_set(ctx)
        ctx, _decision = after_human_resolution(
            ctx,
            action_ids=resolved_action_ids,
            reason=f"Safety finding {finding_id} resolved as {status}.",
            source="safety_resolution",
        )
        self._store().save(ctx)
        self._cache_set(ctx)
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
