# core/services/evaluation.py
"""Evaluation, Redteam and trace-backfill operations."""

from __future__ import annotations

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
from core.oversight_service import (
    create_actions_from_eval_failures,
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
from core.services.access import (
    SessionAccess,
)
from core.target_testing import TargetSystemConfig, sanitize_endpoint
from core.trace_backfill_service import (
    convert_trace_to_eval_case,
    create_dataset_from_failed_traces,
)


class EvaluationService(SessionAccess):
    def list_eval_cases(self, session_id: str, tenant_id: str = "") -> list[dict]:
        rows = self._projection_rows("eval_cases", session_id, tenant_id)
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
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
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
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

    def list_eval_runs(
        self, session_id: str, eval_id: str | None = None, tenant_id: str = ""
    ) -> list[dict]:
        rows = self._projection_rows(
            "eval_runs", session_id, tenant_id, {"eval_id": eval_id} if eval_id else None
        )
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
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
        target_config: TargetSystemConfig | None = None,
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        runs = execute_eval_cases(
            ctx,
            eval_ids=eval_ids,
            run_mode=run_mode,
            target_config=target_config,
        )
        run_payloads = [run.model_dump(mode="json") for run in runs]
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
            session_id=session_id,
            event_type="eval_cases_run",
            stage=3,
            payload={
                "eval_ids": eval_ids or "all",
                "run_mode": run_mode,
                "created_runs": len(runs),
                "target_endpoint": (
                    sanitize_endpoint(target_config.endpoint) if target_config is not None else ""
                ),
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

    def list_eval_datasets(self, session_id: str, tenant_id: str = "") -> list[dict]:
        rows = self._projection_rows("eval_datasets", session_id, tenant_id)
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [dataset.model_dump(mode="json") for dataset in list_datasets(ctx)]

    def get_eval_dataset(self, session_id: str, dataset_id: str, tenant_id: str = "") -> dict:
        ctx = self.get_session(session_id, tenant_id)
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
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = create_dataset_from_stage3(
            ctx,
            name=name,
            description=description,
            version=version,
            owner=owner,
        )
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
        self,
        session_id: str,
        *,
        dataset_id: str,
        eval_ids: list[str],
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = add_cases_to_dataset(ctx, dataset_id=dataset_id, eval_ids=eval_ids)
        self._store().save(ctx)
        self._cache_set(ctx)
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
        self,
        session_id: str,
        *,
        dataset_id: str,
        eval_ids: list[str],
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = remove_cases_from_dataset(ctx, dataset_id=dataset_id, eval_ids=eval_ids)
        self._store().save(ctx)
        self._cache_set(ctx)
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
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        dataset = set_dataset_baseline(
            ctx,
            dataset_id=dataset_id,
            baseline_experiment_id=baseline_experiment_id,
        )
        self._store().save(ctx)
        self._cache_set(ctx)
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

    def list_eval_experiments(self, session_id: str, tenant_id: str = "") -> list[dict]:
        rows = self._projection_rows("eval_experiments", session_id, tenant_id)
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [experiment.model_dump(mode="json") for experiment in list_experiments(ctx)]

    def get_eval_experiment(self, session_id: str, experiment_id: str, tenant_id: str = "") -> dict:
        ctx = self.get_session(session_id, tenant_id)
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
        target_config: TargetSystemConfig | None = None,
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        config = dict(run_config or {})
        if target_config is not None:
            config["target_config"] = {
                "endpoint": sanitize_endpoint(target_config.endpoint),
                "timeout_seconds": target_config.timeout_seconds,
                "output_field": target_config.output_field,
            }
        experiment = create_experiment(
            ctx,
            dataset_id=dataset_id,
            name=name,
            description=description,
            run_mode=run_mode,
            provider=provider,
            model=model,
            baseline_experiment_id=baseline_experiment_id,
            run_config=config,
        )
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
        self,
        session_id: str,
        *,
        experiment_id: str,
        dry_run_only: bool = True,
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        experiment = run_experiment(ctx, experiment_id=experiment_id, dry_run_only=dry_run_only)
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def get_eval_experiment_metrics(
        self, session_id: str, experiment_id: str, tenant_id: str = ""
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
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
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        comparison = compare_experiment_with_baseline(
            ctx,
            experiment_id=experiment_id,
            baseline_experiment_id=baseline_experiment_id,
        )
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def list_eval_judgments(
        self,
        session_id: str,
        *,
        eval_run_id: str | None = None,
        experiment_id: str | None = None,
        tenant_id: str = "",
    ) -> list[dict]:
        ctx = self.get_session(session_id, tenant_id)
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
        tenant_id: str = "",
    ) -> list[dict]:
        ctx = self.get_session(session_id, tenant_id)
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
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def trace_to_eval_case(
        self,
        session_id: str,
        *,
        trace_id: str,
        expected_behavior: str | None = None,
        target_node_id: str | None = None,
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        eval_case = convert_trace_to_eval_case(
            ctx,
            trace_id=trace_id,
            expected_behavior=expected_behavior,
            target_node_id=target_node_id,
        )
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def list_redteam_cases(self, session_id: str, tenant_id: str = "") -> list[dict]:
        rows = self._projection_rows("redteam_cases", session_id, tenant_id)
        if rows is not None:
            return rows
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return [case.model_dump(mode="json") for case in list_redteam_cases_operation(ctx)]

    def redteam_coverage_summary(self, session_id: str, tenant_id: str = "") -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        return build_redteam_coverage_summary(ctx, stage=3)

    def generate_redteam_cases(
        self, session_id: str, *, stage: int = 3, tenant_id: str = ""
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        cases = generate_redteam_cases_operation(ctx, stage=stage)
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def create_redteam_case(self, session_id: str, tenant_id: str = "", **kwargs) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        case = create_redteam_case_operation(ctx, generated_by="human", **kwargs)
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def approve_redteam_case(
        self, session_id: str, case_id: str, *, note: str = "", tenant_id: str = ""
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        case = approve_redteam_case_operation(ctx, case_id, note=note)
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def reject_redteam_case(
        self, session_id: str, case_id: str, *, note: str = "", tenant_id: str = ""
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        case = reject_redteam_case_operation(ctx, case_id, note=note)
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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

    def redteam_case_to_eval_case(self, session_id: str, case_id: str, tenant_id: str = "") -> dict:
        ctx = self.get_session(session_id, tenant_id)
        if not ctx:
            raise ValueError(f"Session not found: {session_id}")
        eval_case = redteam_case_to_eval_case_operation(ctx, case_id)
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
        tenant_id: str = "",
    ) -> dict:
        ctx = self.get_session(session_id, tenant_id)
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
        self._store().save(ctx)
        self._cache_set(ctx)
        self._log_event(
            ctx,
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
