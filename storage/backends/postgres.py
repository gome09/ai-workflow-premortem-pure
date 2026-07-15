# storage/backends/postgres.py
"""PostgreSQL session-store backend (moved from storage/session_store.py)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from core.config import settings
from core.migrations import migrate_context
from core.models import ProjectContext
from storage.field_security import decrypt_fields_after_load, encrypt_fields_for_storage

logger = logging.getLogger(__name__)


class PostgresSessionStore:
    """PostgreSQL 会话持久化"""

    # TODO: _sync_* 方法太多且结构重复，后面应该抽象一个通用的 upsert 方法
    # 不过现在能用就没急着改

    def __init__(self):
        self._dsn = settings.postgres_dsn_sync

    def _get_conn(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def initialize(self) -> None:
        """Run alembic migrations to head. Called once at app startup."""
        import shutil
        import subprocess
        import sys

        alembic_bin = shutil.which("alembic") or str(
            __import__("pathlib").Path(sys.executable).parent / "alembic"
        )
        result = subprocess.run(  # noqa: S603  # alembic command, input is controlled
            [alembic_bin, "upgrade", "head"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Alembic migration failed: %s", result.stderr)
            raise RuntimeError(f"Database migration failed:\n{result.stderr}")
        logger.info("Database migrations applied. %s", result.stdout.strip())

    @staticmethod
    def _build_context_json_for_storage(ctx: ProjectContext) -> str:
        """序列化 context_json，截断大字段以避免超过 PostgreSQL JSONB 256MB 限制。

        LLM traces、eval runs、audit events 等已通过 _sync_* 方法写入独立表，
        context_json 只保留摘要信息。
        """
        data = ctx.model_dump(mode="json")

        # Truncate LLM trace metadata — full traces are in llm_traces table
        truncated_traces = []
        for trace in data.get("llm_traces", []):
            meta = trace.get("metadata") or {}
            truncated_traces.append(
                {
                    "trace_id": trace.get("trace_id"),
                    "session_id": trace.get("session_id"),
                    "stage": trace.get("stage"),
                    "node_name": trace.get("node_name"),
                    "trace_type": trace.get("trace_type"),
                    "model": trace.get("model"),
                    "input_token_count": trace.get("input_token_count"),
                    "output_token_count": trace.get("output_token_count"),
                    "estimated_cost": trace.get("estimated_cost"),
                    "latency_ms": trace.get("latency_ms"),
                    "parser_status": trace.get("parser_status"),
                    "safety_status": trace.get("safety_status"),
                    "error_type": trace.get("error_type"),
                    "created_at": trace.get("created_at"),
                    "metadata_keys": list(meta.keys()) if meta else [],
                }
            )
        data["llm_traces"] = truncated_traces

        # Truncate audit event snapshots — full events are in audit_events table
        truncated_audit = []
        for event in data.get("audit_events", []):
            truncated_audit.append(
                {
                    "event_id": event.get("event_id"),
                    "session_id": event.get("session_id"),
                    "actor": event.get("actor"),
                    "event_type": event.get("event_type"),
                    "target_type": event.get("target_type"),
                    "target_id": event.get("target_id"),
                    "created_at": event.get("created_at"),
                    # before_snapshot / after_snapshot / metadata omitted — full data in audit_events table
                }
            )
        data["audit_events"] = truncated_audit

        # Truncate report artifact content — full data is in report_artifacts table
        truncated_reports = []
        for artifact in data.get("report_artifacts", []):
            truncated_reports.append(
                {
                    "report_id": artifact.get("report_id"),
                    "session_id": artifact.get("session_id"),
                    "version": artifact.get("version"),
                    "generated_at": artifact.get("generated_at"),
                    # content_json / content_markdown omitted — full data in report_artifacts table
                }
            )
        data["report_artifacts"] = truncated_reports

        # T1.3: encrypt sensitive fields before serialization
        encrypt_fields_for_storage(data, ctx.data_classification)

        return json.dumps(data, default=str)

    def save(self, ctx: ProjectContext) -> None:
        """创建或更新会话"""
        ctx.updated_at = datetime.utcnow()
        sql = """
            INSERT INTO sessions (session_id, tenant_id, current_state, context_json, created_at, updated_at)
            VALUES (%s, %s::uuid, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                current_state = EXCLUDED.current_state,
                context_json  = EXCLUDED.context_json,
                updated_at    = EXCLUDED.updated_at
        """
        with self._get_conn() as conn:
            conn.execute(
                sql,
                (
                    ctx.session_id,
                    ctx.tenant_id or None,
                    ctx.current_state.value,
                    self._build_context_json_for_storage(ctx),
                    ctx.created_at,
                    ctx.updated_at,
                ),
            )
            self._sync_human_actions(conn, ctx)
            self._sync_action_resolution_logs(conn, ctx)
            self._sync_llm_traces(conn, ctx)
            self._sync_audit_events(conn, ctx)
            self._sync_evidence_sources(conn, ctx)
            self._sync_safety_findings(conn, ctx)
            self._sync_report_artifacts(conn, ctx)
            self._sync_eval_cases(conn, ctx)
            self._sync_eval_runs(conn, ctx)
            self._sync_eval_judgments(conn, ctx)
            self._sync_human_calibrations(conn, ctx)
            self._sync_eval_datasets(conn, ctx)
            self._sync_eval_experiments(conn, ctx)
            self._sync_redteam_cases(conn, ctx)
            self._sync_interrupt_records(conn, ctx)
            conn.commit()

    def _sync_human_actions(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步 ProjectContext 中的人工动作到索引表。使用 upsert，避免删除历史。"""
        for action in ctx.pending_actions:
            conn.execute(
                """
                INSERT INTO human_actions (
                    action_id, session_id, stage_id, node_id, source_type, source_id,
                    action_type, status, risk_level, title, description, trigger_reason,
                    blocking, payload_before, payload_after, reviewer_decision,
                    reviewer_note, stage_output_version, superseded_by,
                    action_contract_id, action_schema_version, idempotency_key,
                    target_stage, target_stage_version, target_object_path,
                    expected_before_hash, approved_payload_hash, resume_token, expires_at,
                    resolution_attempts, last_resolution_error, created_at, resolved_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (action_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    payload_after = EXCLUDED.payload_after,
                    reviewer_decision = EXCLUDED.reviewer_decision,
                    reviewer_note = EXCLUDED.reviewer_note,
                    stage_output_version = EXCLUDED.stage_output_version,
                    superseded_by = EXCLUDED.superseded_by,
                    idempotency_key = EXCLUDED.idempotency_key,
                    target_stage = EXCLUDED.target_stage,
                    target_stage_version = EXCLUDED.target_stage_version,
                    target_object_path = EXCLUDED.target_object_path,
                    expected_before_hash = EXCLUDED.expected_before_hash,
                    approved_payload_hash = EXCLUDED.approved_payload_hash,
                    resume_token = EXCLUDED.resume_token,
                    expires_at = EXCLUDED.expires_at,
                    resolution_attempts = EXCLUDED.resolution_attempts,
                    last_resolution_error = EXCLUDED.last_resolution_error,
                    resolved_at = EXCLUDED.resolved_at
                """,
                (
                    action.action_id,
                    ctx.session_id,
                    action.stage_id,
                    action.node_id,
                    action.source_type,
                    action.source_id,
                    action.action_type,
                    action.status,
                    action.risk_level,
                    action.title,
                    action.description,
                    action.trigger_reason,
                    action.blocking,
                    json.dumps(action.payload_before, default=str),
                    json.dumps(action.payload_after, default=str)
                    if action.payload_after is not None
                    else None,
                    action.reviewer_decision,
                    action.reviewer_note,
                    action.stage_output_version,
                    action.superseded_by,
                    action.action_contract_id,
                    action.action_schema_version,
                    action.idempotency_key,
                    action.target_stage,
                    action.target_stage_version,
                    action.target_object_path,
                    action.expected_before_hash,
                    action.approved_payload_hash,
                    action.resume_token,
                    action.expires_at,
                    action.resolution_attempts,
                    action.last_resolution_error,
                    action.created_at,
                    action.resolved_at,
                ),
            )

    def _sync_action_resolution_logs(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步 action resolution logs。append-only：已存在 log_id 不覆盖。"""
        for log in getattr(ctx, "action_resolution_logs", []) or []:
            conn.execute(
                """
                INSERT INTO action_resolution_logs (
                    log_id, session_id, action_id, idempotency_key, requested_status,
                    result_status, before_hash, after_hash, error_message, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (log_id) DO NOTHING
                """,
                (
                    log.log_id,
                    ctx.session_id,
                    log.action_id,
                    log.idempotency_key,
                    log.requested_status,
                    log.result_status,
                    log.before_hash,
                    log.after_hash,
                    log.error_message,
                    log.created_at,
                ),
            )

    def _sync_llm_traces(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步 LLM traces。append-only：已存在 trace_id 不覆盖。"""
        for trace in getattr(ctx, "llm_traces", []) or []:
            conn.execute(
                """
                INSERT INTO llm_traces (
                    trace_id, session_id, stage, node_name, trace_type, provider, model,
                    prompt_template_id, prompt_template_version, input_token_count,
                    output_token_count, estimated_cost, latency_ms, retry_count,
                    parser_status, safety_status, evidence_count, error_type,
                    error_message, metadata, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trace_id) DO NOTHING
                """,
                (
                    trace.trace_id,
                    ctx.session_id,
                    trace.stage,
                    trace.node_name,
                    trace.trace_type,
                    trace.provider,
                    trace.model,
                    trace.prompt_template_id,
                    trace.prompt_template_version,
                    trace.input_token_count,
                    trace.output_token_count,
                    trace.estimated_cost,
                    trace.latency_ms,
                    trace.retry_count,
                    trace.parser_status,
                    trace.safety_status,
                    trace.evidence_count,
                    trace.error_type,
                    trace.error_message,
                    json.dumps(trace.metadata, default=str),
                    trace.created_at,
                ),
            )

    @staticmethod
    def _truncate_snapshot(snapshot: dict | None, max_bytes: int = 50_000) -> dict | None:
        """Truncate a snapshot dict if its JSON representation exceeds max_bytes."""
        if snapshot is None:
            return None
        raw = json.dumps(snapshot, default=str)
        if len(raw.encode("utf-8")) <= max_bytes:
            return snapshot
        truncated = {}
        for key, value in snapshot.items():
            val_str = json.dumps(value, default=str)
            if len(val_str.encode("utf-8")) > 5_000:
                truncated[key] = f"<truncated: {len(val_str)} bytes>"
            else:
                truncated[key] = value
        truncated["_truncated"] = True
        truncated["_original_size_bytes"] = len(raw.encode("utf-8"))
        return truncated

    def _sync_audit_events(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步审计事件。append-only：已存在 event_id 不覆盖、不删除。"""
        for event in ctx.audit_events:
            conn.execute(
                """
                INSERT INTO audit_events (
                    event_id, session_id, actor, event_type, target_type, target_id,
                    before_hash, after_hash, before_snapshot, after_snapshot, metadata, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event.event_id,
                    ctx.session_id,
                    event.actor,
                    event.event_type,
                    event.target_type,
                    event.target_id,
                    event.before_hash,
                    event.after_hash,
                    json.dumps(self._truncate_snapshot(event.before_snapshot), default=str)
                    if event.before_snapshot is not None
                    else None,
                    json.dumps(self._truncate_snapshot(event.after_snapshot), default=str)
                    if event.after_snapshot is not None
                    else None,
                    json.dumps(event.metadata, default=str),
                    event.created_at,
                ),
            )

    def _sync_evidence_sources(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for ev in ctx.evidence_sources:
            conn.execute(
                """
                INSERT INTO evidence_sources (
                    evidence_id, session_id, title, url, source_type, credibility_score,
                    summary, claims, used_by_failure_mode_ids, verified, verified_by,
                    verified_at, verification_note, retrieved_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (evidence_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    url = EXCLUDED.url,
                    source_type = EXCLUDED.source_type,
                    credibility_score = EXCLUDED.credibility_score,
                    summary = EXCLUDED.summary,
                    claims = EXCLUDED.claims,
                    used_by_failure_mode_ids = EXCLUDED.used_by_failure_mode_ids,
                    verified = EXCLUDED.verified,
                    verified_by = EXCLUDED.verified_by,
                    verified_at = EXCLUDED.verified_at,
                    verification_note = EXCLUDED.verification_note
                """,
                (
                    ev.evidence_id,
                    ctx.session_id,
                    ev.title,
                    ev.url,
                    ev.source_type,
                    ev.credibility_score,
                    ev.summary,
                    json.dumps(ev.claims, default=str),
                    json.dumps(ev.used_by_failure_mode_ids, default=str),
                    ev.verified,
                    ev.verified_by,
                    ev.verified_at,
                    ev.verification_note,
                    ev.retrieved_at,
                ),
            )

    def _sync_safety_findings(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for finding in ctx.safety_findings:
            conn.execute(
                """
                INSERT INTO safety_findings (
                    finding_id, session_id, stage_id, risk_type, severity, location,
                    description, recommended_action, requires_human_review, status,
                    taxonomy_refs, control_refs, mitigation_status, residual_risk,
                    resolution_note, resolved_at, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (finding_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    recommended_action = EXCLUDED.recommended_action,
                    requires_human_review = EXCLUDED.requires_human_review,
                    taxonomy_refs = EXCLUDED.taxonomy_refs,
                    control_refs = EXCLUDED.control_refs,
                    mitigation_status = EXCLUDED.mitigation_status,
                    residual_risk = EXCLUDED.residual_risk,
                    resolution_note = EXCLUDED.resolution_note,
                    resolved_at = EXCLUDED.resolved_at
                """,
                (
                    finding.finding_id,
                    ctx.session_id,
                    finding.stage_id,
                    finding.risk_type,
                    finding.severity,
                    finding.location,
                    finding.description,
                    finding.recommended_action,
                    finding.requires_human_review,
                    finding.status,
                    json.dumps(getattr(finding, "taxonomy_refs", []), default=str),
                    json.dumps(getattr(finding, "control_refs", []), default=str),
                    getattr(finding, "mitigation_status", "open"),
                    getattr(finding, "residual_risk", "unknown"),
                    finding.resolution_note,
                    finding.resolved_at,
                    finding.created_at,
                ),
            )

    @staticmethod
    def _truncate_report_content_json(content_json: dict) -> dict:
        """Truncate large fields in report content_json for DB storage."""
        truncated = dict(content_json)
        if "audit_events" in truncated:
            truncated["audit_events"] = [
                {
                    "event_id": ev.get("event_id"),
                    "actor": ev.get("actor"),
                    "event_type": ev.get("event_type"),
                    "target_type": ev.get("target_type"),
                    "target_id": ev.get("target_id"),
                    "created_at": ev.get("created_at"),
                }
                for ev in truncated["audit_events"]
            ]
        return truncated

    def _sync_report_artifacts(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for artifact in ctx.report_artifacts:
            truncated_content = self._truncate_report_content_json(artifact.content_json)
            conn.execute(
                """
                INSERT INTO report_artifacts (
                    report_id, session_id, version, content_json, content_markdown, generated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE SET
                    version = EXCLUDED.version,
                    content_json = EXCLUDED.content_json,
                    content_markdown = EXCLUDED.content_markdown
                """,
                (
                    artifact.report_id,
                    ctx.session_id,
                    artifact.version,
                    json.dumps(truncated_content, default=str),
                    artifact.content_markdown,
                    artifact.generated_at,
                ),
            )

    def _sync_eval_cases(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for case in ctx.eval_cases:
            conn.execute(
                """
                INSERT INTO eval_cases (
                    eval_id, session_id, stage_id, target_node_id, covered_failure_mode_ids,
                    scenario_type, source_type, source_trace_id, source_ref_id, metadata,
                    input_payload, expected_behavior, pass_criteria, actual_output, human_score,
                    human_comment, passed, created_at, scored_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (eval_id) DO UPDATE SET
                    covered_failure_mode_ids = EXCLUDED.covered_failure_mode_ids,
                    source_type = EXCLUDED.source_type,
                    source_trace_id = EXCLUDED.source_trace_id,
                    source_ref_id = EXCLUDED.source_ref_id,
                    metadata = EXCLUDED.metadata,
                    pass_criteria = EXCLUDED.pass_criteria,
                    actual_output = EXCLUDED.actual_output,
                    human_score = EXCLUDED.human_score,
                    human_comment = EXCLUDED.human_comment,
                    passed = EXCLUDED.passed,
                    scored_at = EXCLUDED.scored_at
                """,
                (
                    case.eval_id,
                    ctx.session_id,
                    case.stage_id,
                    case.target_node_id,
                    json.dumps(case.covered_failure_mode_ids, default=str),
                    case.scenario_type,
                    getattr(case, "source_type", "stage3_generated"),
                    getattr(case, "source_trace_id", None),
                    getattr(case, "source_ref_id", None),
                    json.dumps(getattr(case, "metadata", {}), default=str),
                    case.input_payload,
                    case.expected_behavior,
                    json.dumps(case.pass_criteria, default=str),
                    case.actual_output,
                    case.human_score,
                    case.human_comment,
                    case.passed,
                    case.created_at,
                    case.scored_at,
                ),
            )

    def _sync_eval_runs(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for run in ctx.eval_runs:
            conn.execute(
                """
                INSERT INTO eval_runs (
                    run_id, session_id, eval_id, dataset_id, experiment_id, run_index,
                    target_node_id, covered_failure_mode_ids,
                    stage_output_version, run_mode, input_payload, expected_behavior,
                    actual_output, judge_result, judge_reason, judge_mode, violated_criteria,
                    status, error_message, trace_id, latency_ms, estimated_cost, created_at, completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    dataset_id = EXCLUDED.dataset_id,
                    experiment_id = EXCLUDED.experiment_id,
                    run_index = EXCLUDED.run_index,
                    actual_output = EXCLUDED.actual_output,
                    judge_result = EXCLUDED.judge_result,
                    judge_reason = EXCLUDED.judge_reason,
                    judge_mode = EXCLUDED.judge_mode,
                    violated_criteria = EXCLUDED.violated_criteria,
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    trace_id = EXCLUDED.trace_id,
                    latency_ms = EXCLUDED.latency_ms,
                    estimated_cost = EXCLUDED.estimated_cost,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    run.run_id,
                    ctx.session_id,
                    run.eval_id,
                    run.dataset_id,
                    run.experiment_id,
                    run.run_index,
                    run.target_node_id,
                    json.dumps(run.covered_failure_mode_ids, default=str),
                    run.stage_output_version,
                    run.run_mode,
                    run.input_payload,
                    run.expected_behavior,
                    run.actual_output,
                    run.judge_result,
                    run.judge_reason,
                    run.judge_mode,
                    json.dumps(run.violated_criteria, default=str),
                    run.status,
                    run.error_message,
                    run.trace_id,
                    run.latency_ms,
                    run.estimated_cost,
                    run.created_at,
                    run.completed_at,
                ),
            )

    def _sync_eval_judgments(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for judgment in getattr(ctx, "eval_judgments", []) or []:
            conn.execute(
                """
                INSERT INTO eval_judgments (
                    judgment_id, session_id, eval_run_id, eval_id, experiment_id, judge_type,
                    judge_model, score, label, rationale, uncertainty, cited_rules, payload_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (judgment_id) DO UPDATE SET
                    label = EXCLUDED.label,
                    rationale = EXCLUDED.rationale,
                    uncertainty = EXCLUDED.uncertainty,
                    cited_rules = EXCLUDED.cited_rules,
                    payload_json = EXCLUDED.payload_json
                """,
                (
                    judgment.judgment_id,
                    ctx.session_id,
                    judgment.eval_run_id,
                    judgment.eval_id,
                    judgment.experiment_id,
                    judgment.judge_type,
                    judgment.judge_model,
                    judgment.score,
                    judgment.label,
                    judgment.rationale,
                    judgment.uncertainty,
                    json.dumps(judgment.cited_rules, default=str),
                    json.dumps(judgment.model_dump(mode="json"), default=str),
                    judgment.created_at,
                ),
            )

    def _sync_human_calibrations(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for calibration in getattr(ctx, "human_calibrations", []) or []:
            conn.execute(
                """
                INSERT INTO human_calibrations (
                    calibration_id, session_id, eval_run_id, eval_id, experiment_id, human_label,
                    human_comment, judge_label, agreement, disagreement_reason, reviewer_id,
                    payload_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (calibration_id) DO UPDATE SET
                    human_label = EXCLUDED.human_label,
                    human_comment = EXCLUDED.human_comment,
                    judge_label = EXCLUDED.judge_label,
                    agreement = EXCLUDED.agreement,
                    disagreement_reason = EXCLUDED.disagreement_reason,
                    reviewer_id = EXCLUDED.reviewer_id,
                    payload_json = EXCLUDED.payload_json
                """,
                (
                    calibration.calibration_id,
                    ctx.session_id,
                    calibration.eval_run_id,
                    calibration.eval_id,
                    calibration.experiment_id,
                    calibration.human_label,
                    calibration.human_comment,
                    calibration.judge_label,
                    calibration.agreement,
                    calibration.disagreement_reason,
                    calibration.reviewer_id,
                    json.dumps(calibration.model_dump(mode="json"), default=str),
                    calibration.created_at,
                ),
            )

    def _sync_eval_datasets(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for dataset in getattr(ctx, "eval_datasets", []) or []:
            conn.execute(
                """
                INSERT INTO eval_datasets (
                    dataset_id, session_id, name, version, source, stage, scenario_type,
                    case_ids, payload_json, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    version = EXCLUDED.version,
                    source = EXCLUDED.source,
                    stage = EXCLUDED.stage,
                    scenario_type = EXCLUDED.scenario_type,
                    case_ids = EXCLUDED.case_ids,
                    payload_json = EXCLUDED.payload_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    dataset.dataset_id,
                    ctx.session_id,
                    dataset.name,
                    dataset.version,
                    dataset.source,
                    dataset.stage,
                    dataset.scenario_type,
                    json.dumps(dataset.case_ids, default=str),
                    json.dumps(dataset.model_dump(mode="json"), default=str),
                    dataset.created_at,
                    dataset.updated_at,
                ),
            )

    def _sync_eval_experiments(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for experiment in getattr(ctx, "eval_experiments", []) or []:
            conn.execute(
                """
                INSERT INTO eval_experiments (
                    experiment_id, session_id, dataset_id, name, status, run_mode, provider,
                    model, baseline_experiment_id, eval_ids, run_ids, aggregate_metrics,
                    comparison_summary, payload_json, created_at, started_at, completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (experiment_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    run_mode = EXCLUDED.run_mode,
                    provider = EXCLUDED.provider,
                    model = EXCLUDED.model,
                    baseline_experiment_id = EXCLUDED.baseline_experiment_id,
                    eval_ids = EXCLUDED.eval_ids,
                    run_ids = EXCLUDED.run_ids,
                    aggregate_metrics = EXCLUDED.aggregate_metrics,
                    comparison_summary = EXCLUDED.comparison_summary,
                    payload_json = EXCLUDED.payload_json,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    experiment.experiment_id,
                    ctx.session_id,
                    experiment.dataset_id,
                    experiment.name,
                    experiment.status,
                    experiment.run_mode,
                    experiment.provider,
                    experiment.model,
                    experiment.baseline_experiment_id,
                    json.dumps(experiment.eval_ids, default=str),
                    json.dumps(experiment.run_ids, default=str),
                    json.dumps(experiment.aggregate_metrics.model_dump(mode="json"), default=str),
                    json.dumps(experiment.comparison_summary, default=str),
                    json.dumps(experiment.model_dump(mode="json"), default=str),
                    experiment.created_at,
                    experiment.started_at,
                    experiment.completed_at,
                ),
            )

    def _sync_redteam_cases(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for case in getattr(ctx, "redteam_cases", []) or []:
            conn.execute(
                """
                INSERT INTO redteam_cases (
                    redteam_case_id, session_id, target_stage, target_node_id,
                    source_finding_id, source_failure_mode_id, attack_type, severity,
                    status, linked_eval_case_id, taxonomy_refs, control_refs,
                    payload_json, created_at, approved_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (redteam_case_id) DO UPDATE SET
                    target_stage = EXCLUDED.target_stage,
                    target_node_id = EXCLUDED.target_node_id,
                    source_finding_id = EXCLUDED.source_finding_id,
                    source_failure_mode_id = EXCLUDED.source_failure_mode_id,
                    attack_type = EXCLUDED.attack_type,
                    severity = EXCLUDED.severity,
                    status = EXCLUDED.status,
                    linked_eval_case_id = EXCLUDED.linked_eval_case_id,
                    taxonomy_refs = EXCLUDED.taxonomy_refs,
                    control_refs = EXCLUDED.control_refs,
                    payload_json = EXCLUDED.payload_json,
                    approved_at = EXCLUDED.approved_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    case.redteam_case_id,
                    ctx.session_id,
                    case.target_stage,
                    case.target_node_id,
                    case.source_finding_id,
                    case.source_failure_mode_id,
                    case.attack_type,
                    case.severity,
                    case.status,
                    case.linked_eval_case_id,
                    json.dumps(getattr(case, "taxonomy_refs", []), default=str),
                    json.dumps(getattr(case, "control_refs", []), default=str),
                    json.dumps(case.model_dump(mode="json"), default=str),
                    case.created_at,
                    case.approved_at,
                    case.updated_at,
                ),
            )

    def _sync_interrupt_records(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步业务中断记录。"""
        for record in getattr(ctx, "interrupt_records", []) or []:
            conn.execute(
                """
                INSERT INTO interrupt_records (
                    interrupt_id, session_id, action_id, stage_id, stage_output_version,
                    status, resume_value, thread_id, node_name, checkpoint_ns,
                    interrupt_payload, resume_consumed_at, created_at, resolved_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (interrupt_id) DO UPDATE SET
                    action_id = EXCLUDED.action_id,
                    stage_id = EXCLUDED.stage_id,
                    stage_output_version = EXCLUDED.stage_output_version,
                    status = EXCLUDED.status,
                    resume_value = EXCLUDED.resume_value,
                    thread_id = EXCLUDED.thread_id,
                    node_name = EXCLUDED.node_name,
                    checkpoint_ns = EXCLUDED.checkpoint_ns,
                    interrupt_payload = EXCLUDED.interrupt_payload,
                    resume_consumed_at = EXCLUDED.resume_consumed_at,
                    resolved_at = EXCLUDED.resolved_at
                """,
                (
                    record.interrupt_id,
                    ctx.session_id,
                    record.action_id,
                    record.stage_id,
                    record.stage_output_version,
                    record.status,
                    json.dumps(record.resume_value, default=str)
                    if record.resume_value is not None
                    else None,
                    record.thread_id,
                    record.node_name,
                    record.checkpoint_ns,
                    json.dumps(record.interrupt_payload, default=str)
                    if record.interrupt_payload is not None
                    else None,
                    record.resume_consumed_at,
                    record.created_at,
                    record.resolved_at,
                ),
            )

    def list_interrupt_records(self, session_id: str) -> list[dict]:
        """从独立 interrupt_records 表读取执行中断记录。"""
        sql = """
            SELECT interrupt_id, session_id, action_id, stage_id, stage_output_version,
                   status, resume_value, thread_id, node_name, checkpoint_ns,
                   interrupt_payload, resume_consumed_at, created_at, resolved_at
            FROM interrupt_records
            WHERE session_id = %s
            ORDER BY created_at DESC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (session_id,)).fetchall()
        return [self._interrupt_row_to_dict(row) for row in rows]

    def get_interrupt_record(self, session_id: str, interrupt_id: str) -> dict | None:
        """读取单条执行中断记录。"""
        sql = """
            SELECT interrupt_id, session_id, action_id, stage_id, stage_output_version,
                   status, resume_value, thread_id, node_name, checkpoint_ns,
                   interrupt_payload, resume_consumed_at, created_at, resolved_at
            FROM interrupt_records
            WHERE session_id = %s AND interrupt_id = %s
        """
        with self._get_conn() as conn:
            row = conn.execute(sql, (session_id, interrupt_id)).fetchone()
        if not row:
            return None
        return self._interrupt_row_to_dict(row)

    @staticmethod
    def _interrupt_row_to_dict(row: dict) -> dict:
        item = dict(row)
        for key in ("created_at", "resolved_at", "resume_consumed_at"):
            if item.get(key) and hasattr(item[key], "isoformat"):
                item[key] = item[key].isoformat()
        return item

    def list_report_artifacts(self, session_id: str) -> list[dict]:
        """从独立 report_artifacts 表读取报告快照列表。"""
        sql = """
            SELECT report_id, session_id, version, content_json, content_markdown, generated_at
            FROM report_artifacts
            WHERE session_id = %s
            ORDER BY generated_at DESC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (session_id,)).fetchall()
        artifacts: list[dict] = []
        for row in rows:
            content = row.get("content_json") or {}
            artifacts.append(
                {
                    "report_id": row["report_id"],
                    "session_id": row["session_id"],
                    "version": row["version"],
                    "generated_at": row["generated_at"].isoformat()
                    if row.get("generated_at")
                    else None,
                    "content_json": content,
                    "content_markdown": row.get("content_markdown") or "",
                    "ai_generated": content.get("ai_generated", {}),
                    "human_reviewed": content.get("human_reviewed", {}),
                    "evidence": content.get("evidence_sources", []),
                    "audit_events": content.get("audit_events", []),
                    "open_risks": content.get("open_risks", []),
                    "eval_summary": content.get("eval_summary", {}),
                    "eval_runs": content.get("eval_runs", []),
                    "failed_eval_runs": content.get("failed_eval_runs", []),
                }
            )
        return artifacts

    def get_report_artifact(self, session_id: str, report_id: str) -> dict | None:
        """从独立 report_artifacts 表读取单个报告快照。"""
        sql = """
            SELECT report_id, session_id, version, content_json, content_markdown, generated_at
            FROM report_artifacts
            WHERE session_id = %s AND report_id = %s
        """
        with self._get_conn() as conn:
            row = conn.execute(sql, (session_id, report_id)).fetchone()
        if not row:
            return None
        content = row.get("content_json") or {}
        return {
            "report_id": row["report_id"],
            "session_id": row["session_id"],
            "version": row["version"],
            "generated_at": row["generated_at"].isoformat() if row.get("generated_at") else None,
            "content_json": content,
            "content_markdown": row.get("content_markdown") or "",
            "ai_generated": content.get("ai_generated", {}),
            "human_reviewed": content.get("human_reviewed", {}),
            "evidence": content.get("evidence_sources", []),
            "audit_events": content.get("audit_events", []),
            "open_risks": content.get("open_risks", []),
            "eval_summary": content.get("eval_summary", {}),
            "eval_runs": content.get("eval_runs", []),
            "failed_eval_runs": content.get("failed_eval_runs", []),
        }

    def load(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
        """加载会话，不存在或 tenant 不匹配则返回 None"""
        if tenant_id:
            sql = "SELECT context_json, tenant_id::text FROM sessions WHERE session_id = %s AND tenant_id = %s::uuid"
            params = (session_id, tenant_id)
        else:
            sql = "SELECT context_json, tenant_id::text FROM sessions WHERE session_id = %s"
            params = (session_id,)
        with self._get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
        if not row:
            return None
        ctx = migrate_context(row["context_json"])
        if ctx:
            decrypt_fields_after_load(ctx)
            if row.get("tenant_id"):
                ctx.tenant_id = row["tenant_id"]
        return ctx

    def archive_audit_events(self, session_id: str, purged_by: str, summary: dict) -> int:
        """Copy audit_events to audit_events_archive + write session_purged event.

        Returns the number of events archived (including the purge event).
        """
        import json
        import uuid

        archived = 0
        with self._get_conn() as conn:
            # Copy existing audit events
            rows = conn.execute(
                "SELECT event_id, actor, event_type, target_type, target_id, "
                "before_hash, after_hash, before_snapshot, after_snapshot, metadata, created_at "
                "FROM audit_events WHERE session_id = %s",
                (session_id,),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "INSERT INTO audit_events_archive "
                    "(archive_id, original_session_id, event_id, actor, event_type, "
                    "target_type, target_id, before_hash, after_hash, before_snapshot, "
                    "after_snapshot, metadata, original_created_at, archived_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()) "
                    "ON CONFLICT (archive_id) DO NOTHING",
                    (
                        f"arch-{row['event_id']}",
                        session_id,
                        row["event_id"],
                        row["actor"],
                        row["event_type"],
                        row["target_type"],
                        row["target_id"],
                        row["before_hash"],
                        row["after_hash"],
                        row["before_snapshot"],
                        row["after_snapshot"],
                        row["metadata"],
                        row["created_at"],
                    ),
                )
                archived += 1

            # Write session_purged event
            conn.execute(
                "INSERT INTO audit_events_archive "
                "(archive_id, original_session_id, event_id, actor, event_type, "
                "target_type, target_id, before_hash, after_hash, before_snapshot, "
                "after_snapshot, metadata, original_created_at, archived_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s, %s, NOW(), NOW())",
                (
                    f"arch-purged-{uuid.uuid4()}",
                    session_id,
                    f"purge-{uuid.uuid4()}",
                    purged_by,
                    "session_purged",
                    "session",
                    session_id,
                    json.dumps(summary, default=str),
                    json.dumps({"purged_by": purged_by}, default=str),
                ),
            )
            archived += 1
            conn.commit()
        return archived

    def delete(self, session_id: str, tenant_id: str = "") -> bool:
        """Delete a session row. Returns True if a row was deleted."""
        with self._get_conn() as conn:
            if tenant_id:
                cur = conn.execute(
                    "DELETE FROM sessions WHERE session_id = %s AND tenant_id = %s::uuid",
                    (session_id, tenant_id),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM sessions WHERE session_id = %s",
                    (session_id,),
                )
            conn.commit()
            return cur.rowcount > 0

    def list_sessions(self, limit: int = 20, tenant_id: str = "") -> list[dict]:
        """列出最近的会话（用于前端历史列表）"""
        if tenant_id:
            sql = """
                SELECT session_id, current_state, created_at, updated_at,
                       context_json->>'research_target' AS research_target,
                       context_json->>'domain' AS domain
                FROM sessions
                WHERE tenant_id = %s::uuid
                ORDER BY updated_at DESC
                LIMIT %s
            """
            params = (tenant_id, limit)
        else:
            sql = """
                SELECT session_id, current_state, created_at, updated_at,
                       context_json->>'research_target' AS research_target,
                       context_json->>'domain' AS domain
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT %s
            """
            params = (limit,)
        with self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def log_event(
        self,
        session_id: str,
        event_type: str,
        stage: int | None,
        payload: dict,
    ) -> None:
        """记录会话事件（用于审计和调试）"""
        sql = """
            INSERT INTO session_events (session_id, event_type, stage, payload)
            VALUES (%s, %s, %s, %s)
        """
        with self._get_conn() as conn:
            conn.execute(sql, (session_id, event_type, stage, json.dumps(payload, default=str)))
            conn.commit()

    # ── Auth methods ──────────────────────────────────────────────────────────

    def create_tenant(self, name: str) -> dict:
        """Create a new tenant, return tenant_id."""
        sql = "INSERT INTO tenants (name) VALUES (%s) RETURNING tenant_id::text, name, created_at"
        with self._get_conn() as conn:
            row = conn.execute(sql, (name,)).fetchone()
            conn.commit()
        return dict(row)

    def create_user(
        self, tenant_id: str, email: str, password_hash: str, role: str = "viewer"
    ) -> dict:
        """Create a user. Raises on duplicate email."""
        sql = """
            INSERT INTO users (tenant_id, email, password_hash, role)
            VALUES (%s::uuid, %s, %s, %s)
            RETURNING user_id::text, tenant_id::text, email, role, created_at
        """
        with self._get_conn() as conn:
            row = conn.execute(sql, (tenant_id, email, password_hash, role)).fetchone()
            conn.commit()
        return dict(row)

    def get_user_by_email(self, email: str) -> dict | None:
        """Lookup user by email for login."""
        sql = "SELECT user_id::text, tenant_id::text, email, password_hash, role FROM users WHERE email = %s"
        with self._get_conn() as conn:
            row = conn.execute(sql, (email,)).fetchone()
        return dict(row) if row else None

    def count_users(self) -> int:
        """Return total number of users (for first-admin bootstrap)."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            return row["n"] if row else 0

    def list_users_by_tenant(self, tenant_id: str) -> list[dict]:
        """List all users belonging to a tenant."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT user_id, tenant_id, email, role, created_at "
                "FROM users WHERE tenant_id = %s ORDER BY created_at",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_user_role(self, user_id: str, tenant_id: str, new_role: str) -> dict | None:
        """Update role for a user within the same tenant. Returns updated user or None."""
        with self._get_conn() as conn:
            row = conn.execute(
                "UPDATE users SET role = %s "
                "WHERE user_id = %s AND tenant_id = %s "
                "RETURNING user_id, tenant_id, email, role",
                (new_role, user_id, tenant_id),
            ).fetchone()
            conn.commit()
            return dict(row) if row else None

    # ── Governance trend analytics (T3.2) ─────────────────────────────────────

    def record_gate_evaluation(
        self,
        *,
        session_id: str,
        tenant_id: str,
        stage_id: int,
        risk_tier: str,
        passed: bool,
        blocking_rule_ids: list,
        rule_versions: dict,
    ) -> None:
        """旁路写入单行评估记录——治理趋势数据源。"""
        import uuid

        record_id = str(uuid.uuid4())[:8]
        sql = """
            INSERT INTO gate_evaluation_records (
                record_id, session_id, tenant_id, stage_id, risk_tier, passed,
                blocking_rule_ids, rule_versions, evaluated_at
            ) VALUES (%s, %s, %s::uuid, %s, %s, %s, %s, %s, NOW())
        """
        with self._get_conn() as conn:
            conn.execute(
                sql,
                (
                    record_id,
                    session_id,
                    tenant_id or None,
                    stage_id,
                    risk_tier,
                    passed,
                    json.dumps(blocking_rule_ids, default=str),
                    json.dumps(rule_versions, default=str),
                ),
            )
            conn.commit()

    def gate_trends(self, tenant_id: str, weeks: int = 8) -> list[dict]:
        """按周聚合门禁评估趋势。空 tenant_id 不开放跨租户查询。"""
        if not tenant_id:
            return []
        sql = """
            SELECT date_trunc('week', evaluated_at)::date::text AS week,
                   passed,
                   blocking_rule_ids
            FROM gate_evaluation_records
            WHERE tenant_id = %s::uuid
              AND evaluated_at >= NOW() - (%s || ' weeks')::INTERVAL
            ORDER BY week DESC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (tenant_id, str(weeks))).fetchall()
        return _aggregate_gate_trends(rows)

    def governance_overview(self, tenant_id: str) -> dict:
        """租户内治理总览聚合。空 tenant_id 返回零值字典。"""
        zero = {
            "sessions_total": 0,
            "state_distribution": {},
            "risk_tier_distribution": {},
            "open_safety_findings": 0,
            "pending_actions": 0,
            "reports_exported": 0,
        }
        if not tenant_id:
            return zero
        with self._get_conn() as conn:
            state_rows = conn.execute(
                "SELECT current_state, COUNT(*) AS n FROM sessions "
                "WHERE tenant_id = %s::uuid GROUP BY current_state",
                (tenant_id,),
            ).fetchall()
            ctx_rows = conn.execute(
                "SELECT session_id, context_json FROM sessions WHERE tenant_id = %s::uuid",
                (tenant_id,),
            ).fetchall()
            eval_rows = conn.execute(
                "SELECT session_id, risk_tier, evaluated_at "
                "FROM gate_evaluation_records WHERE tenant_id = %s::uuid",
                (tenant_id,),
            ).fetchall()
        return _aggregate_governance_overview(state_rows, ctx_rows, eval_rows, zero)

    def actions_backlog(self, tenant_id: str, limit: int = 50) -> list[dict]:
        """待处理人工动作明细，按 risk_level + 等待时长排序。空 tenant_id 返回空列表。"""
        if not tenant_id:
            return []
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT session_id, context_json FROM sessions WHERE tenant_id = %s::uuid",
                (tenant_id,),
            ).fetchall()
        return _aggregate_actions_backlog(rows, limit)


def _aggregate_gate_trends(rows: list[dict]) -> list[dict]:
    """Shared weekly-bucket aggregation for gate_trends."""
    from collections import Counter

    buckets: dict[str, dict] = {}
    for row in rows:
        week = row["week"]
        bucket = buckets.setdefault(week, {"evaluations": 0, "passed": 0, "rules": []})
        bucket["evaluations"] += 1
        if row["passed"]:
            bucket["passed"] += 1
        br_ids = row["blocking_rule_ids"]
        if isinstance(br_ids, str):
            br_ids = json.loads(br_ids) if br_ids else []
        bucket["rules"].extend(br_ids or [])

    result = []
    for week, data in sorted(buckets.items(), reverse=True):
        evaluations = data["evaluations"]
        passed = data["passed"]
        rule_counts = Counter(data["rules"]).most_common(5)
        result.append(
            {
                "week": week,
                "evaluations": evaluations,
                "passed": passed,
                "pass_rate": passed / evaluations if evaluations else 0.0,
                "top_blocking_rules": [{"rule_id": r, "count": c} for r, c in rule_counts],
            }
        )
    return result


def _aggregate_governance_overview(
    state_rows: list[dict], ctx_rows: list[dict], eval_rows: list[dict], zero: dict
) -> dict:
    """Shared governance-overview aggregation."""
    state_distribution: dict[str, int] = {}
    sessions_total = 0
    for row in state_rows:
        state = row["current_state"]
        cnt = row["n"]
        state_distribution[state] = cnt
        sessions_total += cnt

    # risk_tier_distribution: latest risk_tier per session
    latest_by_session: dict[str, tuple] = {}
    for row in eval_rows:
        sid = row["session_id"]
        evaluated_at = row["evaluated_at"]
        cur = latest_by_session.get(sid)
        if cur is None or evaluated_at > cur[0]:
            latest_by_session[sid] = (evaluated_at, row["risk_tier"])
    risk_tier_distribution: dict[str, int] = {}
    for _, tier in latest_by_session.values():
        risk_tier_distribution[tier] = risk_tier_distribution.get(tier, 0) + 1

    open_safety_findings = 0
    pending_actions = 0
    reports_exported = 0
    for row in ctx_rows:
        raw = row.get("context_json") or "{}"
        ctx_data = json.loads(raw) if isinstance(raw, str) else raw
        for finding in ctx_data.get("safety_findings", []) or []:
            if finding.get("status") == "open":
                open_safety_findings += 1
        for action in ctx_data.get("pending_actions", []) or []:
            if action.get("status") == "pending":
                pending_actions += 1
        if ctx_data.get("report_artifacts"):
            reports_exported += 1

    return {
        "sessions_total": sessions_total,
        "state_distribution": state_distribution,
        "risk_tier_distribution": risk_tier_distribution,
        "open_safety_findings": open_safety_findings,
        "pending_actions": pending_actions,
        "reports_exported": reports_exported,
    }


def _aggregate_actions_backlog(rows: list[dict], limit: int) -> list[dict]:
    """Shared actions-backlog aggregation."""
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    actions: list[dict] = []
    for row in rows:
        session_id = row["session_id"]
        raw = row.get("context_json") or "{}"
        ctx_data = json.loads(raw) if isinstance(raw, str) else raw
        for action in ctx_data.get("pending_actions", []) or []:
            if action.get("status") == "pending":
                actions.append(
                    {
                        "session_id": session_id,
                        "action_id": action.get("action_id"),
                        "title": action.get("title"),
                        "risk_level": action.get("risk_level", "medium"),
                        "stage_id": action.get("stage_id"),
                        "created_at": action.get("created_at"),
                    }
                )
    actions.sort(key=lambda a: (risk_order.get(a["risk_level"], 4), a.get("created_at") or ""))
    return actions[:limit]
