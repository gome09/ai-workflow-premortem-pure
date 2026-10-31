# core/services/governance.py
"""Human-action review and risk-profile governance."""

from __future__ import annotations

from core.execution_service import (
    prepare_execution_after_action_resolutions,
)
from core.models import FlagStatus, ProjectContext
from core.oversight_service import (
    resolve_action as resolve_human_action,
)
from core.oversight_service import (
    resolve_action_with_result as resolve_human_action_with_result,
)
from core.oversight_service import (
    resolve_actions_for_flag,
)
from core.risk.assessment import (
    apply_risk_override,
    risk_profile_response,
)
from core.risk.assessment import set_risk_profile as set_risk_profile_factors
from core.risk.models import RiskFactorScores
from core.services.access import (
    SessionAccess,
    _sha256,
)
from core.stage_advancement_coordinator import (
    after_human_resolution,
    append_action_resolution_trace,
    build_stage_advancement_decision,
)
from core.stage_resolution_service import get_next_required_operation


class GovernanceService(SessionAccess):
    def resolve_flag(
        self,
        session_id: str,
        flag_id: str,
        action: str,  # 'verified' | 'dismissed'
        note: str = "",
        tenant_id: str = "",
    ) -> dict:
        """处理【需核验】项，并同步处理由该 flag 派生的人工动作。"""
        from datetime import datetime

        ctx = self.get_session(session_id, tenant_id)
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
        prepare_execution_after_action_resolutions(ctx, resolved_action_ids)
        self._store().save(ctx)
        self._cache_set(ctx)
        ctx, _decision = after_human_resolution(
            ctx,
            action_ids=resolved_action_ids,
            reason=f"Flag {flag_id} resolved as {action}.",
            source="flag_resolution",
        )

        self._store().save(ctx)
        self._cache_set(ctx)
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

    def list_actions(
        self, session_id: str, status: str | None = None, tenant_id: str = ""
    ) -> list[dict]:
        """列出人工监督动作。"""
        rows = self._projection_rows(
            "human_actions",
            session_id,
            tenant_id,
            {"status": status} if status else None,
        )
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        actions = ctx.pending_actions
        if status:
            actions = [action for action in actions if action.status == status]
        return [action.model_dump(mode="json") for action in actions]

    def get_action(self, session_id: str, action_id: str, tenant_id: str = "") -> dict:
        """获取单个人工监督动作。"""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")

        for action in ctx.pending_actions:
            if action.action_id == action_id:
                return action.model_dump(mode="json")
        raise ValueError(f"Action not found: {action_id}")

    def list_action_resolution_logs(
        self, session_id: str, action_id: str, tenant_id: str = ""
    ) -> list[dict]:
        """List append-only resolution attempts for one human action."""
        rows = self._projection_rows(
            "action_resolution_logs", session_id, tenant_id, {"action_id": action_id}
        )
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
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
        tenant_id: str = "",
    ) -> dict:
        """Resolve a formal human action and return the action-resolution result contract."""
        ctx = self.get_session(session_id, tenant_id)
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
            metadata={
                "decision": decision,
                "log_id": result.log_id,
                "note_sha256": _sha256(note),
                "note_length": len(note),
            },
        )
        safe_stage = action_stage or self._current_stage(ctx) or 1
        if result.result_status in {"resolved", "idempotent_replay"}:
            # Persist the human decision before checkpoint resume. A checkpoint
            # outage must never roll back or lose an accepted review decision.
            prepare_execution_after_action_resolutions(ctx, [action_id])
            self._store().save(ctx)
            self._cache_set(ctx)
            ctx, stage_decision = after_human_resolution(
                ctx,
                action_ids=[action_id],
                reason=note or f"Action {action_id} resolved as {decision}.",
                source="action_resolution",
                stage=safe_stage,
            )
            self._log_event(
                ctx,
                session_id=session_id,
                event_type="human_action_resolved",
                stage=self._current_stage(ctx),
                payload={
                    "action_id": action_id,
                    "decision": decision,
                    "note_sha256": _sha256(note),
                    "note_length": len(note),
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

        self._store().save(ctx)
        self._cache_set(ctx)

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
        tenant_id: str = "",
    ) -> ProjectContext:
        """处理正式人工监督动作。"""
        ctx = self.get_session(session_id, tenant_id)
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
            # Persist resolution_attempts / failure logs without advancing execution.
            self._store().save(ctx)
            self._cache_set(ctx)
            raise
        prepare_execution_after_action_resolutions(ctx, [action_id])
        self._store().save(ctx)
        self._cache_set(ctx)
        ctx, stage_decision = after_human_resolution(
            ctx,
            action_ids=[action_id],
            reason=note or f"Action {action_id} resolved as {decision}.",
            source="action_resolution",
        )

        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def get_risk_profile(self, session_id: str, tenant_id: str = "") -> dict:
        """Return the deterministic risk assessment and override history."""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return risk_profile_response(ctx)

    def set_risk_profile(
        self,
        session_id: str,
        *,
        impact: int,
        autonomy: int,
        data_sensitivity: int,
        reversibility: int,
        scale: int,
        external_exposure: int,
        rationale: str = "",
        actor: str = "user",
        actor_role: str = "",
        tenant_id: str = "",
    ) -> dict:
        """Persist explicit six-factor scores for the session."""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        factors = RiskFactorScores(
            impact=impact,
            autonomy=autonomy,
            data_sensitivity=data_sensitivity,
            reversibility=reversibility,
            scale=scale,
            external_exposure=external_exposure,
            rationale=rationale,
            source="human",
        )
        set_risk_profile_factors(ctx, factors, actor=actor, actor_role=actor_role, note=rationale)
        self._save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
            session_id=session_id,
            event_type="risk_profile_updated",
            stage=self._current_stage(ctx),
            payload={
                "factors": factors.as_dict(),
                "actor": actor,
                "actor_role": actor_role,
                "tenant_id": tenant_id,
            },
        )
        return risk_profile_response(ctx)

    def override_risk_tier(
        self,
        session_id: str,
        *,
        requested_tier: str,
        reason: str,
        actor: str = "user",
        actor_role: str = "",
        tenant_id: str = "",
    ) -> dict:
        """Record a human risk-tier override and return the refreshed profile."""
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        record = apply_risk_override(
            ctx,
            requested_tier=requested_tier,
            reason=reason,
            actor=actor,
            actor_role=actor_role,
        )
        self._save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
            session_id=session_id,
            event_type="risk_tier_overridden",
            stage=self._current_stage(ctx),
            payload=record.model_dump(mode="json"),
        )
        return risk_profile_response(ctx)
