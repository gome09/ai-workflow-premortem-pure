# core/session_service.py
"""Compatibility facade for domain services.

SessionService keeps the historical API surface while delegating to
Session/Workflow, Governance, Evidence, Evaluation and Audit/Trace services.
Storage globals stay in this module so existing test patch points keep working.
"""

from __future__ import annotations

import logging

from core.execution_service import execute_one_turn  # noqa: F401 - patch target
from core.models import ProjectContext
from core.services.access import (  # noqa: F401 - compatibility re-exports
    DATA_CLASSIFICATION_ORDER,
    DataClassification,
    SessionAccess,
    _sha256,
)
from core.services.access import (
    DataClassificationDowngradeError as DataClassificationDowngradeError,
)
from core.services.audit_trace import AuditTraceService
from core.services.evaluation import EvaluationService
from core.services.evidence import EvidenceService
from core.services.governance import GovernanceService
from core.services.session_workflow import SessionWorkflowService
from core.stage_advancement_decision import DecisionSource
from storage.cache import context_cache  # noqa: F401 - patch target
from storage.session_store import session_store  # noqa: F401 - patch target

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self) -> None:
        self._access = SessionAccess()

        def _get_session(session_id: str, tenant_id: str = ""):
            # Dynamic attribute lookup preserves tests that patch
            # ``service.get_session`` on the facade instance.
            return self.get_session(session_id, tenant_id)

        self._workflow = SessionWorkflowService(_get_session)
        self._governance = GovernanceService(_get_session)
        self._evidence = EvidenceService(_get_session)
        self._evaluation = EvaluationService(_get_session)
        self._audit = AuditTraceService(_get_session)

    def create_session(
        self,
        tenant_id: str = "",
        scenario_id: str | None = None,
        created_by: str = "",
    ) -> ProjectContext:
        return self._workflow.create_session(tenant_id, scenario_id, created_by)

    def get_session(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
        return self._access.get_session(session_id, tenant_id)

    def get_session_overview(self, session_id: str, tenant_id: str = "") -> dict | None:
        return self._workflow.get_session_overview(session_id, tenant_id)

    def rename_session(self, session_id: str, name: str, tenant_id: str = "") -> dict:
        return self._workflow.rename_session(session_id, name, tenant_id)

    def update_data_classification(
        self,
        session_id: str,
        *,
        data_classification: DataClassification,
        note: str = "",
        actor_role: str = "",
        tenant_id: str = "",
    ) -> dict:
        return self._workflow.update_data_classification(
            session_id,
            data_classification=data_classification,
            note=note,
            actor_role=actor_role,
            tenant_id=tenant_id,
        )

    def delete_session(
        self, session_id: str, *, purged_by: str = "admin", tenant_id: str = ""
    ) -> dict:
        return self._workflow.delete_session(session_id, purged_by=purged_by, tenant_id=tenant_id)

    def list_sessions(self, limit: int = 20, tenant_id: str = "", offset: int = 0) -> list[dict]:
        return self._workflow.list_sessions(limit, tenant_id, offset)

    def recover_workflow(
        self, session_id: str, *, target_state: str, note: str = "", tenant_id: str = ""
    ) -> dict:
        return self._workflow.recover_workflow(
            session_id, target_state=target_state, note=note, tenant_id=tenant_id
        )

    def send_message(
        self,
        session_id: str,
        user_input: str,
        user_materials: list[str] | None = None,
        tenant_id: str = "",
    ) -> tuple[str, ProjectContext]:
        return self._workflow.send_message(session_id, user_input, user_materials, tenant_id)

    def add_materials(self, session_id: str, materials: list[str], tenant_id: str = "") -> dict:
        return self._workflow.add_materials(session_id, materials, tenant_id)

    def resolve_flag(
        self, session_id: str, flag_id: str, action: str, note: str = "", tenant_id: str = ""
    ) -> dict:
        return self._governance.resolve_flag(session_id, flag_id, action, note, tenant_id)

    def list_actions(
        self, session_id: str, status: str | None = None, tenant_id: str = ""
    ) -> list[dict]:
        return self._governance.list_actions(session_id, status, tenant_id)

    def get_action(self, session_id: str, action_id: str, tenant_id: str = "") -> dict:
        return self._governance.get_action(session_id, action_id, tenant_id)

    def list_action_resolution_logs(
        self, session_id: str, action_id: str, tenant_id: str = ""
    ) -> list[dict]:
        return self._governance.list_action_resolution_logs(session_id, action_id, tenant_id)

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
        actor_id: str = "",
        actor_role: str = "",
    ) -> dict:
        return self._governance.resolve_action_with_result(
            session_id,
            action_id,
            decision,
            note,
            payload_after,
            idempotency_key,
            expected_before_hash,
            tenant_id,
            actor_id,
            actor_role,
        )

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
        actor_id: str = "",
        actor_role: str = "",
    ) -> ProjectContext:
        return self._governance.resolve_action(
            session_id,
            action_id,
            decision,
            note,
            payload_after,
            idempotency_key,
            expected_before_hash,
            tenant_id,
            actor_id,
            actor_role,
        )

    def list_traces(
        self,
        session_id: str,
        stage: int | None = None,
        trace_type: str | None = None,
        parser_status: str | None = None,
        tenant_id: str = "",
    ) -> list[dict]:
        return self._audit.list_traces(session_id, stage, trace_type, parser_status, tenant_id)

    def get_trace(self, session_id: str, trace_id: str, tenant_id: str = "") -> dict:
        return self._audit.get_trace(session_id, trace_id, tenant_id)

    def list_audit_events(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._audit.list_audit_events(session_id, tenant_id)

    def list_interrupt_records(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._audit.list_interrupt_records(session_id, tenant_id)

    def get_interrupt_record(self, session_id: str, interrupt_id: str, tenant_id: str = "") -> dict:
        return self._audit.get_interrupt_record(session_id, interrupt_id, tenant_id)

    def list_evidence(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._evidence.list_evidence(session_id, tenant_id)

    def get_evidence(self, session_id: str, evidence_id: str, tenant_id: str = "") -> dict:
        return self._evidence.get_evidence(session_id, evidence_id, tenant_id)

    def verify_evidence(
        self, session_id: str, evidence_id: str, note: str = "", tenant_id: str = ""
    ) -> dict:
        return self._evidence.verify_evidence(session_id, evidence_id, note, tenant_id)

    def list_safety_findings(
        self, session_id: str, status: str | None = None, tenant_id: str = ""
    ) -> list[dict]:
        return self._evidence.list_safety_findings(session_id, status, tenant_id)

    def resolve_safety_finding(
        self, session_id: str, finding_id: str, status: str, note: str = "", tenant_id: str = ""
    ) -> dict:
        return self._evidence.resolve_safety_finding(
            session_id, finding_id, status, note, tenant_id
        )

    def create_report_artifact(self, session_id: str, tenant_id: str = "") -> dict:
        return self._workflow.create_report_artifact(session_id, tenant_id)

    def list_report_artifacts(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._workflow.list_report_artifacts(session_id, tenant_id)

    def get_report_artifact(self, session_id: str, report_id: str, tenant_id: str = "") -> dict:
        return self._workflow.get_report_artifact(session_id, report_id, tenant_id)

    def list_eval_cases(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._evaluation.list_eval_cases(session_id, tenant_id)

    def score_eval_case(
        self,
        session_id: str,
        eval_id: str,
        human_score: int | None = None,
        human_comment: str = "",
        passed: bool | None = None,
        actual_output: str | None = None,
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.score_eval_case(
            session_id, eval_id, human_score, human_comment, passed, actual_output, tenant_id
        )

    def list_eval_runs(
        self, session_id: str, eval_id: str | None = None, tenant_id: str = ""
    ) -> list[dict]:
        return self._evaluation.list_eval_runs(session_id, eval_id, tenant_id)

    def run_eval_cases(
        self,
        session_id: str,
        eval_ids: list[str] | None = None,
        run_mode: str = "manual",
        target_config=None,
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.run_eval_cases(
            session_id,
            eval_ids=eval_ids,
            run_mode=run_mode,
            target_config=target_config,
            tenant_id=tenant_id,
        )

    def list_eval_datasets(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._evaluation.list_eval_datasets(session_id, tenant_id)

    def get_eval_dataset(self, session_id: str, dataset_id: str, tenant_id: str = "") -> dict:
        return self._evaluation.get_eval_dataset(session_id, dataset_id, tenant_id)

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
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.create_eval_dataset(
            session_id,
            name=name,
            description=description,
            case_ids=case_ids,
            scenario_type=scenario_type,
            source=source,
            version=version,
            tags=tags,
            tenant_id=tenant_id,
        )

    def create_eval_dataset_from_stage3(
        self,
        session_id: str,
        *,
        name: str,
        description: str = "",
        version: str = "0.1",
        owner: str = "system",
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.create_eval_dataset_from_stage3(
            session_id,
            name=name,
            description=description,
            version=version,
            owner=owner,
            tenant_id=tenant_id,
        )

    def add_eval_cases_to_dataset(
        self, session_id: str, *, dataset_id: str, eval_ids: list[str], tenant_id: str = ""
    ) -> dict:
        return self._evaluation.add_eval_cases_to_dataset(
            session_id, dataset_id=dataset_id, eval_ids=eval_ids, tenant_id=tenant_id
        )

    def remove_eval_cases_from_dataset(
        self, session_id: str, *, dataset_id: str, eval_ids: list[str], tenant_id: str = ""
    ) -> dict:
        return self._evaluation.remove_eval_cases_from_dataset(
            session_id, dataset_id=dataset_id, eval_ids=eval_ids, tenant_id=tenant_id
        )

    def set_eval_dataset_baseline(
        self,
        session_id: str,
        *,
        dataset_id: str,
        baseline_experiment_id: str | None,
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.set_eval_dataset_baseline(
            session_id,
            dataset_id=dataset_id,
            baseline_experiment_id=baseline_experiment_id,
            tenant_id=tenant_id,
        )

    def list_eval_experiments(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._evaluation.list_eval_experiments(session_id, tenant_id)

    def get_eval_experiment(self, session_id: str, experiment_id: str, tenant_id: str = "") -> dict:
        return self._evaluation.get_eval_experiment(session_id, experiment_id, tenant_id)

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
        target_config=None,
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.create_eval_experiment(
            session_id,
            dataset_id=dataset_id,
            name=name,
            description=description,
            run_mode=run_mode,
            provider=provider,
            model=model,
            baseline_experiment_id=baseline_experiment_id,
            run_config=run_config,
            target_config=target_config,
            tenant_id=tenant_id,
        )

    def run_eval_experiment(
        self, session_id: str, *, experiment_id: str, dry_run_only: bool = True, tenant_id: str = ""
    ) -> dict:
        return self._evaluation.run_eval_experiment(
            session_id, experiment_id=experiment_id, dry_run_only=dry_run_only, tenant_id=tenant_id
        )

    def get_eval_experiment_metrics(
        self, session_id: str, experiment_id: str, tenant_id: str = ""
    ) -> dict:
        return self._evaluation.get_eval_experiment_metrics(session_id, experiment_id, tenant_id)

    def compare_eval_experiment(
        self,
        session_id: str,
        *,
        experiment_id: str,
        baseline_experiment_id: str | None = None,
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.compare_eval_experiment(
            session_id,
            experiment_id=experiment_id,
            baseline_experiment_id=baseline_experiment_id,
            tenant_id=tenant_id,
        )

    def list_eval_judgments(
        self,
        session_id: str,
        *,
        eval_run_id: str | None = None,
        experiment_id: str | None = None,
        tenant_id: str = "",
    ) -> list[dict]:
        return self._evaluation.list_eval_judgments(
            session_id, eval_run_id=eval_run_id, experiment_id=experiment_id, tenant_id=tenant_id
        )

    def list_human_calibrations(
        self,
        session_id: str,
        *,
        eval_run_id: str | None = None,
        experiment_id: str | None = None,
        tenant_id: str = "",
    ) -> list[dict]:
        return self._evaluation.list_human_calibrations(
            session_id, eval_run_id=eval_run_id, experiment_id=experiment_id, tenant_id=tenant_id
        )

    def calibrate_eval_run(
        self,
        session_id: str,
        *,
        run_id: str,
        human_label: str,
        human_comment: str = "",
        reviewer_id: str = "human_reviewer",
        disagreement_reason: str = "",
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.calibrate_eval_run(
            session_id,
            run_id=run_id,
            human_label=human_label,
            human_comment=human_comment,
            reviewer_id=reviewer_id,
            disagreement_reason=disagreement_reason,
            tenant_id=tenant_id,
        )

    def trace_to_eval_case(
        self,
        session_id: str,
        *,
        trace_id: str,
        expected_behavior: str | None = None,
        target_node_id: str | None = None,
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.trace_to_eval_case(
            session_id,
            trace_id=trace_id,
            expected_behavior=expected_behavior,
            target_node_id=target_node_id,
            tenant_id=tenant_id,
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
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.traces_to_eval_dataset(
            session_id,
            trace_ids=trace_ids,
            name=name,
            description=description,
            version=version,
            owner=owner,
            tenant_id=tenant_id,
        )

    def list_redteam_cases(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._evaluation.list_redteam_cases(session_id, tenant_id)

    def redteam_coverage_summary(self, session_id: str, tenant_id: str = "") -> dict:
        return self._evaluation.redteam_coverage_summary(session_id, tenant_id)

    def generate_redteam_cases(
        self, session_id: str, *, stage: int = 3, tenant_id: str = ""
    ) -> dict:
        return self._evaluation.generate_redteam_cases(session_id, stage=stage, tenant_id=tenant_id)

    def create_redteam_case(self, session_id: str, tenant_id: str = "", **kwargs) -> dict:
        return self._evaluation.create_redteam_case(session_id, tenant_id, **kwargs)

    def approve_redteam_case(
        self, session_id: str, case_id: str, *, note: str = "", tenant_id: str = ""
    ) -> dict:
        return self._evaluation.approve_redteam_case(
            session_id, case_id, note=note, tenant_id=tenant_id
        )

    def reject_redteam_case(
        self, session_id: str, case_id: str, *, note: str = "", tenant_id: str = ""
    ) -> dict:
        return self._evaluation.reject_redteam_case(
            session_id, case_id, note=note, tenant_id=tenant_id
        )

    def redteam_case_to_eval_case(self, session_id: str, case_id: str, tenant_id: str = "") -> dict:
        return self._evaluation.redteam_case_to_eval_case(session_id, case_id, tenant_id)

    def create_redteam_dataset(
        self,
        session_id: str,
        *,
        name: str = "Red Team generated dataset",
        description: str = "Approved RedTeamCase records synced into EvalCase for regression gate use.",
        case_ids: list[str] | None = None,
        version: str = "0.1",
        owner: str = "system",
        tenant_id: str = "",
    ) -> dict:
        return self._evaluation.create_redteam_dataset(
            session_id,
            name=name,
            description=description,
            case_ids=case_ids,
            version=version,
            owner=owner,
            tenant_id=tenant_id,
        )

    def prepare_stage_rerun(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "",
        note: str = "",
        tenant_id: str = "",
    ) -> dict:
        return self._workflow.prepare_stage_rerun(
            session_id, stage_id=stage_id, reason=reason, note=note, tenant_id=tenant_id
        )

    def request_stage_revision(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "",
        note: str = "",
        tenant_id: str = "",
    ) -> dict:
        return self._workflow.request_stage_revision(
            session_id, stage_id=stage_id, reason=reason, note=note, tenant_id=tenant_id
        )

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
        return self._workflow.request_stage_rollback(
            session_id,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=reason,
            note=note,
            target_running=target_running,
            tenant_id=tenant_id,
        )

    def sync_stage_review_actions(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "manual_sync_review_actions",
        tenant_id: str = "",
    ) -> dict:
        return self._workflow.sync_stage_review_actions(
            session_id, stage_id=stage_id, reason=reason, tenant_id=tenant_id
        )

    def get_stage_advancement_decision(
        self, session_id: str, stage_id: int, tenant_id: str = ""
    ) -> dict:
        return self._workflow.get_stage_advancement_decision(session_id, stage_id, tenant_id)

    def advance_stage_if_ready(
        self,
        session_id: str,
        *,
        stage_id: int,
        reason: str = "",
        source: str = "api_advance",
        tenant_id: str = "",
    ) -> dict:
        return self._workflow.advance_stage_if_ready(
            session_id, stage_id=stage_id, reason=reason, source=source, tenant_id=tenant_id
        )

    def export_report(self, session_id: str, format: str = "json", tenant_id: str = "") -> dict:
        return self._workflow.export_report(session_id, format, tenant_id)

    def get_risk_profile(self, session_id: str, tenant_id: str = "") -> dict:
        return self._governance.get_risk_profile(session_id, tenant_id)

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
        return self._governance.set_risk_profile(
            session_id,
            impact=impact,
            autonomy=autonomy,
            data_sensitivity=data_sensitivity,
            reversibility=reversibility,
            scale=scale,
            external_exposure=external_exposure,
            rationale=rationale,
            actor=actor,
            actor_role=actor_role,
            tenant_id=tenant_id,
        )

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
        return self._governance.override_risk_tier(
            session_id,
            requested_tier=requested_tier,
            reason=reason,
            actor=actor,
            actor_role=actor_role,
            tenant_id=tenant_id,
        )

    def list_risk_treatments(self, session_id: str, tenant_id: str = "") -> dict:
        return self._governance.list_risk_treatments(session_id, tenant_id)

    def upsert_risk_treatment(
        self,
        session_id: str,
        *,
        source_type: str,
        source_id: str,
        owner: str,
        mitigation_plan: str,
        status: str,
        actor_id: str,
        actor_role: str,
        note: str = "",
        tenant_id: str = "",
    ) -> dict:
        return self._governance.upsert_risk_treatment(
            session_id,
            source_type=source_type,
            source_id=source_id,
            owner=owner,
            mitigation_plan=mitigation_plan,
            status=status,
            actor_id=actor_id,
            actor_role=actor_role,
            note=note,
            tenant_id=tenant_id,
        )

    def review_risk_treatment(
        self,
        session_id: str,
        *,
        treatment_id: str,
        decision: str,
        note: str,
        actor_id: str,
        actor_role: str,
        tenant_id: str = "",
    ) -> dict:
        return self._governance.review_risk_treatment(
            session_id,
            treatment_id=treatment_id,
            decision=decision,
            note=note,
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
        )

    def get_approval_status(self, session_id: str, tenant_id: str = "") -> dict:
        return self._governance.get_approval_status(session_id, tenant_id)

    def list_project_approvals(self, session_id: str, tenant_id: str = "") -> list[dict]:
        return self._governance.list_project_approvals(session_id, tenant_id)

    def request_release_approval(
        self,
        session_id: str,
        *,
        decision: str,
        note: str,
        actor_id: str,
        actor_role: str,
        tenant_id: str = "",
    ) -> dict:
        return self._governance.request_release_approval(
            session_id,
            decision=decision,
            note=note,
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
        )

    # ── Compatibility helpers (historically tested through the facade) ──
    def _projection_rows(
        self,
        table: str,
        session_id: str,
        tenant_id: str = "",
        filters: dict | None = None,
    ) -> list[dict] | None:
        return self._access._projection_rows(table, session_id, tenant_id, filters=filters)

    def _session_exists(self, session_id: str, tenant_id: str = "") -> bool | None:
        return self._access._session_exists(session_id, tenant_id)

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
        return self._access._with_stage_advancement(
            ctx,
            operation=operation,
            result=result,
            source=source,
            stage=stage,
            reason=reason,
            metadata=metadata,
        )

    def _log_event(
        self,
        ctx: ProjectContext,
        *,
        event_type: str,
        payload: dict | None = None,
        stage: int | None = None,
        session_id: str = "",
    ) -> None:
        self._access._log_event(
            ctx,
            event_type=event_type,
            payload=payload,
            stage=stage,
            session_id=session_id,
        )

    def _current_stage(self, ctx: ProjectContext) -> int | None:
        return self._access._current_stage(ctx)

    def _extract_latest_reply(self, ctx: ProjectContext) -> str:
        return self._access._extract_latest_reply(ctx)

    @staticmethod
    def _build_lightweight_context(ctx: ProjectContext) -> ProjectContext:
        return SessionAccess._build_lightweight_context(ctx)


session_service = SessionService()
